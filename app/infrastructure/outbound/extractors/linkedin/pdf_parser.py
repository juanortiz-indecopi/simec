"""Convierte el PDF de "Guardar en PDF" de LinkedIn en un dict, sin LLM.

El PDF (Apache FOP) tiene una maquetación fija: columna lateral a la izquierda y cuerpo a la derecha,
y el tamaño/color de letra identifica cada elemento (nombre, sección, empresa, cargo, ubicación...).
"""
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from typing import Any

from pdfminer.high_level import extract_pages
from pdfminer.layout import LTChar, LTContainer

ANCHO_LATERAL = 210.0
TAM_NOMBRE = 20.0
TAM_SECCION = 14.5
TAM_SECCION_LATERAL = 12.5
TAM_EMPRESA = 11.8
TAM_CARGO = 11.2

SECCIONES = {
    "contactar": "contact", "contacto": "contact", "contact": "contact",
    "aptitudes principales": "top_skills", "top skills": "top_skills",
    "languages": "languages", "idiomas": "languages",
    "certifications": "certifications", "certificaciones": "certifications",
    "honors-awards": "honors_awards", "honors & awards": "honors_awards",
    "reconocimientos y premios": "honors_awards",
    "publications": "publications", "publicaciones": "publications",
    "patents": "patents", "patentes": "patents",
    "extracto": "summary", "summary": "summary",
    "experiencia": "experience", "experience": "experience",
    "educacion": "education", "education": "education", "formacion": "education",
}
ACTUAL = {"present", "presente", "actualidad", "actual"}
FECHAS_RE = re.compile(r"^(?P<ini>.*?\d{4})\s+[-–]\s+(?P<fin>.+?)(?:\s*\((?P<dur>[^()]*)\))?$")
PAGINA_RE = re.compile(r"^(Page|Página)\s+\d+\s+(of|de)\s+\d+$", re.IGNORECASE)
EDU_FECHAS_RE = re.compile(r"\s*·?\s*\(([^()]*\d{4}[^()]*)\)\s*$")
VINETA_RE = re.compile(r"^(\d{1,2}[.)]\s|[•●▪◦✓✔➤►]|[-–*]\s)")
TOLERANCIA = 14.0  # el corte de renglón de FOP no llega exactamente al margen


@dataclass
class Linea:
    pagina: int
    y: float  # línea base, medida desde arriba
    x1: float
    size: float
    gris: bool
    texto: str
    ancho_primera: float


def _chars(elemento):
    for hijo in elemento:
        if isinstance(hijo, LTChar):
            yield hijo
        elif isinstance(hijo, LTContainer):
            yield from _chars(hijo)


def _es_gris(char: LTChar) -> bool:
    color = char.graphicstate.ncolor
    valores = color if isinstance(color, (tuple, list)) else (color,)
    try:
        return bool(valores) and all(0.5 < float(v) < 0.8 for v in valores)
    except (TypeError, ValueError):
        return False


def _construir_linea(pagina: int, y: float, chars: list[LTChar]) -> Linea | None:
    visibles = sorted((c for c in chars if not c.get_text().isspace()), key=lambda c: c.x0)
    if not visibles:
        return None
    espacios = sorted(c.x0 for c in chars if c.get_text().isspace())
    texto, ancho_primera, previo = "", None, None
    for c in visibles:
        if previo is not None and (
            c.x0 - previo.x1 > c.size * 0.2 or any(previo.x0 < x < c.x0 for x in espacios)
        ):
            texto += " "
            if ancho_primera is None:
                ancho_primera = previo.x1 - visibles[0].x0
        texto += c.get_text()
        previo = c
    texto = " ".join(texto.replace("\x00", "").split())
    if not texto:
        return None
    x1 = visibles[-1].x1
    return Linea(
        pagina=pagina,
        y=y,
        x1=x1,
        size=Counter(round(c.size, 1) for c in visibles).most_common(1)[0][0],
        gris=sum(_es_gris(c) for c in visibles) > len(visibles) / 2,
        texto=texto,
        ancho_primera=ancho_primera or (x1 - visibles[0].x0),
    )


def _leer_lineas(ruta: str) -> tuple[list[Linea], list[Linea]]:
    lateral: list[Linea] = []
    cuerpo: list[Linea] = []
    for n, pagina in enumerate(extract_pages(ruta)):
        todos = list(_chars(pagina))
        for destino, es_lateral in ((lateral, True), (cuerpo, False)):
            filas: dict[int, list[LTChar]] = {}
            for c in todos:
                if (c.x0 < ANCHO_LATERAL) == es_lateral:
                    filas.setdefault(round(pagina.height - c.matrix[5]), []).append(c)
            for y in sorted(filas):
                linea = _construir_linea(n, float(y), filas[y])
                if linea and not PAGINA_RE.match(linea.texto):
                    destino.append(linea)
    return lateral, cuerpo


def _clave(texto: str) -> str:
    base = unicodedata.normalize("NFD", texto).encode("ascii", "ignore").decode()
    base = " ".join(base.lower().split())
    return SECCIONES.get(base) or re.sub(r"[^a-z0-9]+", "_", base).strip("_")


def _seccionar(lineas: list[Linea], tam: float) -> tuple[list[Linea], dict[str, list[Linea]]]:
    previas: list[Linea] = []
    secciones: dict[str, list[Linea]] = {}
    actual = previas
    for ln in lineas:
        if tam <= ln.size < TAM_NOMBRE:
            actual = secciones.setdefault(_clave(ln.texto), [])
        else:
            actual.append(ln)
    return previas, secciones


def _unir(a: str, b: str) -> str:
    """Une dos renglones partidos por ancho; una URL cortada se recompone sin espacio."""
    ultima = a.rsplit(None, 1)[-1]
    es_url = re.match(r"(https?://|www\.)", ultima) and ultima[-1] in "-/"
    return a + ("" if es_url else " ") + b


def _parrafos(lineas: list[Linea], margen: float) -> str | None:
    """Reconstruye párrafos: si la primera palabra siguiente cabía en el renglón, el salto era real."""
    if not lineas:
        return None
    texto, previa = lineas[0].texto, lineas[0]
    for ln in lineas[1:]:
        if ln.pagina == previa.pagina and ln.y - previa.y > 27:
            texto += "\n\n" + ln.texto
        elif VINETA_RE.match(ln.texto) or previa.x1 + previa.size * 0.3 + ln.ancho_primera < margen - TOLERANCIA:
            texto += "\n" + ln.texto
        else:
            texto = _unir(texto, ln.texto)
        previa = ln
    return texto


def _items(lineas: list[Linea]) -> list[str]:
    """Columna lateral: los renglones de un mismo elemento van a ~12.5 pt y los elementos a ~17.5 pt."""
    items: list[str] = []
    previa: Linea | None = None
    for ln in lineas:
        if previa and ln.pagina == previa.pagina and ln.y - previa.y < 15:
            items[-1] += " " + ln.texto
        else:
            items.append(ln.texto)
        previa = ln
    return items


def _contacto(lineas: list[Linea]) -> list[dict[str, str | None]]:
    """Cada entrada es un valor (1+ renglones) y, opcionalmente, su etiqueta: "(LinkedIn)"."""
    entradas: list[dict[str, str | None]] = []
    abierta = False  # la última entrada aún puede continuar en el renglón siguiente
    y_prev: tuple[int, float] | None = None
    for ln in lineas:
        contigua = y_prev is not None and y_prev[0] == ln.pagina and ln.y - y_prev[1] < 14.5
        y_prev = (ln.pagina, ln.y)
        etiqueta = re.fullmatch(r"(.*?)\s*\(([^()]+)\)", ln.texto)
        valor = etiqueta.group(1) if etiqueta else ln.texto
        if valor:
            if abierta and contigua:
                previo = entradas[-1]["value"] or ""
                es_url = "/" in previo or "@" in previo
                entradas[-1]["value"] = previo + ("" if es_url else " ") + valor
            else:
                entradas.append({"value": valor, "label": None})
            abierta = True
        if etiqueta and entradas:
            entradas[-1]["label"] = etiqueta.group(2)
            abierta = False
    return entradas


def _idiomas(lineas: list[Linea]) -> list[dict[str, str | None]]:
    salida = []
    for item in _items(lineas):
        m = re.fullmatch(r"(.+?)\s*\((.+)\)", item)
        salida.append({"name": m.group(1) if m else item, "level": m.group(2) if m else None})
    return salida


def _fechas(texto: str) -> dict[str, Any] | None:
    m = FECHAS_RE.match(texto)
    if not m:
        return None
    actual = m["fin"].strip().lower() in ACTUAL
    if not actual and not re.search(r"\d{4}$", m["fin"]):
        return None
    return {
        "start": m["ini"], "end": None if actual else m["fin"],
        "is_current": actual, "duration": m["dur"],
    }


def _experiencia(lineas: list[Linea], margen: float) -> list[dict[str, Any]]:
    puestos: list[dict[str, Any]] = []
    empresa, total, rol, previo = "", None, None, ""
    for ln in lineas:
        if ln.size >= TAM_EMPRESA:
            empresa = f"{empresa} {ln.texto}" if previo == "empresa" else ln.texto
            total, rol, previo = None, None, "empresa"
        elif ln.size >= TAM_CARGO:
            if previo == "cargo":
                rol["title"] += " " + ln.texto
            else:
                rol = {
                    "company": empresa, "company_total_duration": total, "title": ln.texto,
                    "start": None, "end": None, "is_current": None, "duration": None,
                    "location": None, "_desc": [],
                }
                puestos.append(rol)
            previo = "cargo"
        elif rol is None:
            total, previo = ln.texto, "total"  # empresa con varios cargos: duración acumulada
        elif previo == "cargo" and (fechas := _fechas(ln.texto)):
            rol.update(fechas)
            previo = "fechas"
        elif ln.gris and not rol["_desc"]:
            rol["location"] = f'{rol["location"]} {ln.texto}' if rol["location"] else ln.texto
            previo = "ubicacion"
        else:
            rol["_desc"].append(ln)
            previo = "descripcion"
    for p in puestos:
        p["description"] = _parrafos(p.pop("_desc"), margen)
    return puestos


def _educacion(lineas: list[Linea]) -> list[dict[str, Any]]:
    grupos: list[list[str]] = []
    previa_centro = False
    for ln in lineas:
        es_centro = ln.size >= TAM_EMPRESA
        if es_centro and previa_centro:
            grupos[-1][0] += " " + ln.texto
        elif es_centro:
            grupos.append([ln.texto, ""])
        elif grupos:
            grupos[-1][1] = f"{grupos[-1][1]} {ln.texto}".strip()
        previa_centro = es_centro
    salida = []
    for centro, detalle in grupos:
        inicio = fin = None
        estudio = detalle
        if m := EDU_FECHAS_RE.search(detalle):
            estudio = detalle[: m.start()].strip()
            partes = re.split(r"\s+[-–]\s+", m.group(1).strip(), maxsplit=1)
            inicio, fin = (partes[0], partes[1]) if len(partes) == 2 else (None, partes[0])
        grado, _, campo = estudio.partition(", ")
        salida.append({
            "institution": centro, "degree": grado or None, "field": campo or None,
            "start": inicio, "end": fin, "raw": detalle or None,
        })
    return salida


def parse_perfil_pdf(ruta: str) -> dict[str, Any]:
    lateral, cuerpo = _leer_lineas(ruta)
    _, sec_lat = _seccionar(lateral, TAM_SECCION_LATERAL)
    cabecera, sec = _seccionar(cuerpo, TAM_SECCION)
    margen = max((ln.x1 for ln in cuerpo), default=0.0)

    def unir(filas: list[Linea]) -> str | None:
        return " ".join(ln.texto for ln in filas) or None

    contacto = _contacto(sec_lat.pop("contact", []))
    perfil: dict[str, Any] = {
        "full_name": unir([ln for ln in cabecera if ln.size >= TAM_NOMBRE]),
        "headline": unir([ln for ln in cabecera if ln.size < TAM_NOMBRE and not ln.gris]),
        "location": unir([ln for ln in cabecera if ln.size < TAM_NOMBRE and ln.gris]),
        "contact": contacto,
        "summary": _parrafos(sec.pop("summary", []), margen),
        "experience": _experiencia(sec.pop("experience", []), margen),
        "education": _educacion(sec.pop("education", [])),
        "top_skills": _items(sec_lat.pop("top_skills", [])),
        "languages": _idiomas(sec_lat.pop("languages", [])),
    }
    for clave in ("certifications", "honors_awards", "publications", "patents"):
        perfil[clave] = _items(sec_lat.pop(clave, []))
    # Secciones no previstas: se conservan como texto para no perder información.
    otras: dict[str, Any] = {k: _items(v) for k, v in sec_lat.items()}
    otras.update({k: _parrafos(v, margen) for k, v in sec.items()})
    perfil["other_sections"] = otras
    return perfil
