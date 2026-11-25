"""Compara una página de Facebook con los datos registrales de una empresa (RUC 20).

Todo lo publicado en la página lo escribe su administrador, así que ninguna señal prueba identidad:
el resultado es una sugerencia con motivos para que decida un analista.
"""
import re
import unicodedata
from typing import Final

from app.domain.models.facebook import CompanyFacts, FacebookPage, MatchResult, PageVerification

_LEGAL_FORMS: Final = (
    ("EIRL", r"EMPRESA INDIVIDUAL DE R\w* L\w*|E I R L|EIRL"),
    ("SAC", r"SOCIEDAD ANONIMA CERRADA|S A C|SAC"),
    ("SAA", r"SOCIEDAD ANONIMA ABIERTA|S A A|SAA"),
    ("SRL", r"SOCIEDAD COMERCIAL DE R\w* L\w*|S R L|SRL|S R LTDA|SRLTDA"),
    ("SA", r"SOCIEDAD ANONIMA|S A|SA"),
)
_STOPWORDS: Final = frozenset("A AL DE DEL LA LAS EL LOS Y E AND OF THE EN PARA POR".split())
# Palabras que comparten muchas empresas: por sí solas no identifican a ninguna.
_GENERIC: Final = frozenset(
    "AMERICA ANDINA ANDINO APURIMAC ABANCAY AREQUIPA ASOCIADOS CENTRO COMERCIAL COMERCIALIZADORA COMPANIA "
    "CONSORCIO CONSTRUCCIONES CONSTRUCTORA CONSULTORES CONSULTORIA CONTRATISTAS CORPORACION CUSCO "
    "DISTRIBUIDORA EMPRESA EMPRESAS GENERAL GENERALES GLOBAL GROUP GRUPO IMPORTACIONES INDUSTRIAS "
    "INGENIEROS INMOBILIARIA INTERNACIONAL INTERNET INVERSIONES LIMA MULTISERVICIOS NACIONAL NEGOCIOS "
    "NORTE PERU PERUANA PERUANO PROYECTOS REPRESENTACIONES SERVICE SERVICES SERVICIO SERVICIOS SOLUCIONES "
    "SOLUTIONS SUR TECNOLOGIA TRANSPORTES".split()
)
# Prefijo CIIU -> raíces que suelen aparecer en la categoría o descripción de la página.
_ACTIVITY_ROOTS: Final = {
    "01": ("AGRIC", "AGRO", "GANADER"), "10": ("ALIMENT", "PANADER"), "14": ("ROPA", "TEXTIL"),
    "41": ("CONSTRUC", "INMOBILI"), "42": ("CONSTRUC",), "43": ("CONSTRUC", "INSTALAC"),
    "45": ("AUTOMO", "VEHICUL", "REPUEST"), "49": ("TRANSPORT",), "55": ("HOTEL", "HOSPED"),
    "56": ("RESTAUR", "COMIDA", "CAFETER"), "61": ("INTERNET", "TELECOM", "TELEFON"),
    "62": ("SOFTWARE", "INFORMATIC", "PROGRAMAC"), "63": ("SOFTWARE", "INFORMATIC", "WEB"),
    "68": ("INMOBILI",), "69": ("ABOGAD", "CONTAB", "CONTAD", "LEGAL"), "71": ("INGENIER", "ARQUITECT"),
    "73": ("PUBLICID", "MARKETING"), "79": ("TURISM", "VIAJE"), "80": ("SEGURIDAD", "VIGILANC"),
    "85": ("EDUCA", "ESCUELA", "COLEGIO", "INSTITUTO"), "86": ("SALUD", "MEDIC", "CLINIC", "HOSPITAL"),
    "96": ("BELLEZA", "PELUQU", "LAVANDER"),
}
_STREET: Final = re.compile(
    r"\b(?:JR|JIRON|AV|AVENIDA|CAL|CALLE|PJ|PASAJE|PROLONGACION|CARRETERA)\b (.+?) (?:NRO|NUMERO|NUM|NO)? ?(\d{1,5})\b"
)
_PUBLIC_MAIL: Final = frozenset("GMAIL HOTMAIL OUTLOOK YAHOO LIVE ICLOUD".split())


def _plain(value: str | None) -> str:
    ascii_text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode().upper()
    return " ".join(re.sub(r"[^A-Z0-9]", " ", ascii_text).split())


def split_legal_form(name: str) -> tuple[str, str | None]:
    """("INVERSIONES HUAYNA", "EIRL") a partir de "Inversiones Huayna E.I.R.L."."""
    plain = _plain(name)
    for form, pattern in _LEGAL_FORMS:
        match = re.search(rf" (?:{pattern})$", plain)
        if match:
            return plain[: match.start()], form
    return plain, None


def _tokens(value: str) -> set[str]:
    return set(value.split()) - _STOPWORDS


def _has_tokens(text: str, needed: set[str]) -> bool:
    return bool(needed) and needed <= set(text.split())


def _same_address(registered: str, page_address: str) -> bool:
    match = _STREET.search(_plain(registered))
    if match is None:
        return False
    street, number = match.groups()
    return re.search(rf"\b{re.escape(street)}(?: NRO| NUMERO| NUM| NO)? {number}\b", page_address) is not None


def verify_page(page: FacebookPage, company: CompanyFacts) -> PageVerification:
    reasons: list[str] = []
    warnings: list[str] = []
    page_name, page_form = split_legal_form(page.name)
    page_tokens = _tokens(page_name)
    page_place = _plain(" ".join(x for x in (page.address, page.city) if x))
    topic = _plain(" ".join(x for x in (page.category, page.description) if x))

    published = " ".join(
        x
        for x in (
            page.name,
            page.description,
            page.responsible,
            *(field.value for field in page.other_info),
        )
        if x
    )
    has_ruc = re.search(rf"(?<!\d){company.ruc}(?!\d)", published) is not None
    if has_ruc:
        reasons.append("La página publica el mismo RUC")

    owner = False
    full_name = distinctive = some_distinctive = partial = False
    for name in company.names:
        base, form = split_legal_form(name)
        tokens = _tokens(base)
        special = {t for t in tokens if t not in _GENERIC and len(t) > 2}
        if page.responsible and split_legal_form(page.responsible)[0] == base:
            owner = True
        if tokens and tokens == page_tokens:
            full_name = True
            distinctive = distinctive or bool(special)
        elif special and special <= page_tokens:
            distinctive = True
        elif special & page_tokens:
            some_distinctive = True
        elif tokens & page_tokens:
            partial = True
        if form and page_form and form != page_form:
            warnings.append(f"La forma societaria difiere: {form} en el registro, {page_form} en la página")
        elif form and page_form and (full_name or distinctive):
            reasons.append(f"Coincide la forma societaria ({form})")
        label = "".join(sorted(special)) if len(special) == 1 else ""
        domains = [m.rpartition("@")[2] for m in page.emails]
        domains += [re.sub(r"^https?://", "", link.url).split("/")[0] for link in page.links if link.platform == "WEB"]
        if label and label not in _PUBLIC_MAIL and any(label in d.upper().split(".") for d in domains):
            reasons.append("El dominio de su correo o web coincide con el nombre")
    if owner:
        reasons.append("El responsable de la página coincide con la razón social")
    if distinctive:
        reasons.append("Coincide el nombre distintivo")
    elif full_name:
        reasons.append("Coincide el nombre, aunque es genérico")
    elif some_distinctive:
        reasons.append("Coincide una palabra distintiva del nombre")
    elif partial:
        reasons.append("Coincide parte del nombre (palabras genéricas)")

    city = any(_has_tokens(page_place, set(_plain(place).split())) for place in company.places)
    address = city and any(_same_address(a, page_place) for a in company.addresses)
    if address:
        reasons.append("Coinciden la calle, el número y la ciudad")
    elif city:
        reasons.append("Coincide la ubicación")
    elif page_place and company.places:
        warnings.append("La ubicación publicada no coincide con la registrada")

    roots = {
        root
        for activity in company.activities
        if (code := re.search(r"\b(\d{2})\d{2}\b", activity))
        for root in _ACTIVITY_ROOTS.get(code.group(1), ())
    }
    activity = any(re.search(rf"\b{root}", topic) for root in roots)
    if activity:
        reasons.append("El rubro es compatible")

    any_name = distinctive or full_name or some_distinctive or partial
    if has_ruc or owner or (address and (any_name or activity)) or (distinctive and city):
        result = MatchResult.PROBABLE
    elif distinctive or some_distinctive or address or (any_name and city and activity):
        result = MatchResult.POSSIBLE
    else:
        result = MatchResult.NO_EVIDENCE
        warnings.append("No hay coincidencias suficientes")
    if result is MatchResult.PROBABLE and warnings and not has_ruc:
        result = MatchResult.POSSIBLE
    return PageVerification(
        company.ruc, result, tuple(dict.fromkeys(reasons)), tuple(dict.fromkeys(warnings))
    )
