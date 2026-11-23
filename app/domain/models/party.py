"""Personas, empresas y los vínculos entre ellas.

Regla de identidad: una persona natural con negocio tiene RUC 10 = "10" + DNI (8 dígitos) + dígito
verificador. Ese RUC y el DNI identifican a la misma persona, así que ambos se resuelven a la
misma referencia (documento principal DNI, tax_id con el RUC).
"""
import re
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Final

_DNI: Final = re.compile(r"[0-9]{8}")
_RUC: Final = re.compile(r"[0-9]{11}")
NATURAL_PERSON_RUC_PREFIX: Final = "10"


class PartyType(str, Enum):
    PERSON = "PERSON"
    COMPANY = "COMPANY"


class DocumentType(str, Enum):
    DNI = "DNI"
    RUC = "RUC"
    CE = "CE"
    PASAPORTE = "PASAPORTE"
    OTRO = "OTRO"


class LinkType(str, Enum):
    SHAREHOLDER = "SHAREHOLDER"                      # SEACE: accionista / socio / titular
    LEGAL_REPRESENTATIVE = "LEGAL_REPRESENTATIVE"    # SUNAT: representante legal
    SEACE_LINKED_PROVIDER = "SEACE_LINKED_PROVIDER"  # SEACE por DNI: proveedor donde figura la persona
    OTHER = "OTHER"


def dni_from_natural_person_ruc(ruc: str) -> str | None:
    """DNI contenido en un RUC 10; None si el RUC no es de persona natural con DNI."""
    if _RUC.fullmatch(ruc) and ruc.startswith(NATURAL_PERSON_RUC_PREFIX):
        return ruc[2:10]
    return None


@dataclass(frozen=True, slots=True)
class PartyRef:
    """Identifica a una persona o empresa por su documento principal."""

    party_type: PartyType
    document_type: DocumentType
    document_number: str
    display_name: str
    tax_id: str | None = None

    @classmethod
    def person(cls, dni: str, full_name: str, tax_id: str | None = None) -> "PartyRef":
        if not _DNI.fullmatch(dni):
            raise ValueError("DNI must have exactly 8 digits")
        return cls(PartyType.PERSON, DocumentType.DNI, dni, full_name.strip(), tax_id)

    @classmethod
    def from_ruc(cls, ruc: str, name: str) -> "PartyRef":
        """Un RUC 10 se resuelve a la persona de su DNI; cualquier otro RUC, a una empresa."""
        if not _RUC.fullmatch(ruc):
            raise ValueError("RUC must have exactly 11 digits")
        dni = dni_from_natural_person_ruc(ruc)
        if dni is not None:
            return cls.person(dni, name, tax_id=ruc)
        return cls(PartyType.COMPANY, DocumentType.RUC, ruc, name.strip(), tax_id=ruc)

    @classmethod
    def from_document(cls, document_type: str | None, document_number: str, name: str) -> "PartyRef":
        """Resuelve documentos tal como llegan de las fuentes (SUNAT trae el tipo; SEACE no)."""
        number = document_number.strip()
        kind = (document_type or "").strip().upper()
        if kind in ("", "DNI", "LE", "LIBRETA ELECTORAL") and _DNI.fullmatch(number):
            return cls.person(number, name)
        if kind in ("", "RUC") and _RUC.fullmatch(number):
            return cls.from_ruc(number, name)
        if kind.startswith("CARNE") or kind.startswith("CARNÉ") or kind == "CE":
            return cls(PartyType.PERSON, DocumentType.CE, number, name.strip())
        if kind.startswith("PASAPORTE"):
            return cls(PartyType.PERSON, DocumentType.PASAPORTE, number, name.strip())
        return cls(PartyType.PERSON, DocumentType.OTRO, number, name.strip())


@dataclass(frozen=True, slots=True)
class PartyLink:
    """`holder` ejerce el vínculo sobre `company` (es su accionista, representante, etc.).

    `source_name` es la fuente que lo reporta (AuditResult.source_name): permite saber de qué
    foto salió y desactivarlo si una consulta posterior de esa fuente ya no lo trae.
    """

    holder: PartyRef
    company: PartyRef
    link_type: LinkType
    source_name: str
    role: str | None = None
    share_percentage: float | None = None
    start_date: date | None = None
