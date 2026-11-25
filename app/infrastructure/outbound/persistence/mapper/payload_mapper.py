"""Conversión entre los modelos de dominio (dataclasses) y el JSON guardado en snapshot_payloads.

- `dump`: dataclass -> JSON canónico + hash SHA-256. El JSON lleva "__type__" con el nombre de la
  clase para poder reconstruirla; el hash es estable (claves ordenadas), así que dos consultas con
  el mismo resultado producen el mismo hash y se deduplican.
- `load`: JSON -> dataclass, guiado por las anotaciones de tipo de la clase. Tolera la evolución
  del dominio: los campos nuevos con valor por defecto se completan y las claves que ya no existen
  se ignoran, así las fotos antiguas siguen siendo legibles.

Para persistir una fuente nueva basta con agregar su modelo raíz a PAYLOAD_TYPES.
"""
import dataclasses
import hashlib
import json
import types
from datetime import date, datetime
from enum import Enum
from typing import Any, Final, Union, get_args, get_origin, get_type_hints

from app.domain.models.facebook import FacebookPage
from app.domain.models.instagram import InstagramProfile
from app.domain.models.profile import CompanyProfile, PersonProfile
from app.domain.models.rnp import RnpRecord
from app.domain.models.seace import SeacePersonRecord, SeaceProviderRecord
from app.domain.models.sunarp import SunarpRecord
from app.domain.models.sunat import SunatProfile

TYPE_KEY: Final = "__type__"

PAYLOAD_TYPES: Final[dict[str, type]] = {
    cls.__name__: cls
    for cls in (
        PersonProfile,
        CompanyProfile,
        SunatProfile,
        SeaceProviderRecord,
        SeacePersonRecord,
        RnpRecord,
        SunarpRecord,
        InstagramProfile,
        FacebookPage,
    )
}


class PayloadMappingError(ValueError):
    """El JSON guardado no corresponde a ningún modelo conocido o no se pudo reconstruir."""


def to_jsonable(value: Any) -> Any:
    """Convierte cualquier valor a tipos JSON. PostgreSQL no admite el carácter \\u0000 en JSONB."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, Enum):
        return to_jsonable(value.value)
    if isinstance(value, datetime):  # Antes que date: datetime es subclase de date.
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: to_jsonable(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [to_jsonable(v) for v in value]
    if isinstance(value, (bytes, bytearray)):
        return to_jsonable(bytes(value).decode("utf-8", errors="replace"))
    return to_jsonable(str(value))


def canonical_hash(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def dump(data: Any) -> tuple[dict[str, Any], str]:
    """Modelo de dominio -> (JSON con __type__, hash)."""
    kind = type(data).__name__
    if PAYLOAD_TYPES.get(kind) is not type(data):
        raise PayloadMappingError(f"Modelo no registrado para persistencia: {kind}")
    payload = {TYPE_KEY: kind, **to_jsonable(data)}
    return payload, canonical_hash(payload)


def load(payload: dict[str, Any]) -> Any:
    """JSON guardado -> modelo de dominio."""
    kind = payload.get(TYPE_KEY)
    cls = PAYLOAD_TYPES.get(kind) if isinstance(kind, str) else None
    if cls is None:
        raise PayloadMappingError(f"Tipo de payload desconocido: {kind!r}")
    try:
        return _build(cls, payload)
    except (TypeError, ValueError, KeyError) as exc:
        raise PayloadMappingError(f"No se pudo reconstruir {kind}: {exc}") from exc


def _build(cls: type, data: dict[str, Any]) -> Any:
    hints = get_type_hints(cls)
    kwargs = {
        field.name: _convert(hints[field.name], data[field.name])
        for field in dataclasses.fields(cls)
        if field.name in data
    }
    return cls(**kwargs)


def _convert(tp: Any, value: Any) -> Any:
    if value is None or tp is Any:
        return value
    origin = get_origin(tp)
    if origin in (Union, types.UnionType):
        options = [arg for arg in get_args(tp) if arg is not type(None)]
        if len(options) != 1:
            raise TypeError(f"Unión no soportada: {tp}")
        return _convert(options[0], value)
    if origin is tuple:
        args = get_args(tp)
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_convert(args[0], item) for item in value)
        return tuple(_convert(arg, item) for arg, item in zip(args, value))
    if origin is list:
        (item_type,) = get_args(tp) or (Any,)
        return [_convert(item_type, item) for item in value]
    if origin is dict:
        return dict(value)
    if dataclasses.is_dataclass(tp):
        return _build(tp, value)
    if isinstance(tp, type) and issubclass(tp, Enum):
        return tp(value)
    if tp is datetime:
        return datetime.fromisoformat(value)
    if tp is date:
        return date.fromisoformat(value)
    if tp is float:
        return float(value)
    if tp is int:
        return int(value)
    return value
