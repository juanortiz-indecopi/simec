"""Identifica vínculos entre personas y empresas a partir de lo que reporta cada fuente.

- SUNAT (ficha RUC): representantes legales -> LEGAL_REPRESENTATIVE.
- SEACE (ficha de proveedor): accionistas, socios o titulares -> SHAREHOLDER.
- SEACE (por DNI): proveedores donde figura la persona -> SEACE_LINKED_PROVIDER, más los
  accionistas de cada uno de esos proveedores.

Un registro con documento ilegible se descarta en silencio: un vínculo dudoso no debe impedir
guardar el resto de la consulta.
"""
from collections.abc import Iterator

from app.domain.models.party import LinkType, PartyLink, PartyRef
from app.domain.models.seace import SeacePersonRecord, SeaceProviderRecord
from app.domain.models.sunat import SunatProfile


def _ref(document_type: str | None, document_number: str, name: str) -> PartyRef | None:
    if not document_number or not document_number.strip():
        return None
    try:
        return PartyRef.from_document(document_type, document_number, name or document_number)
    except ValueError:
        return None


def links_from_sunat(profile: SunatProfile, company: PartyRef, source_name: str) -> list[PartyLink]:
    links: list[PartyLink] = []
    for rep in profile.legal_representatives:
        holder = _ref(rep.document_type, rep.document_number, rep.full_name)
        if holder is None:
            continue
        links.append(
            PartyLink(
                holder=holder,
                company=company,
                link_type=LinkType.LEGAL_REPRESENTATIVE,
                source_name=source_name,
                role=rep.role or None,
                start_date=rep.start_date,
            )
        )
    return links


def links_from_seace_provider(
    record: SeaceProviderRecord, company: PartyRef, source_name: str
) -> list[PartyLink]:
    links: list[PartyLink] = []
    for shareholder in record.shareholders:
        holder = _ref(None, shareholder.document_number, shareholder.full_name)
        if holder is None:
            continue
        links.append(
            PartyLink(
                holder=holder,
                company=company,
                link_type=LinkType.SHAREHOLDER,
                source_name=source_name,
                role=shareholder.relationship_type or None,
                share_percentage=shareholder.share_percentage,
            )
        )
    return links


def links_from_seace_person(
    record: SeacePersonRecord, person: PartyRef, source_name: str
) -> list[PartyLink]:
    links: list[PartyLink] = []
    for linked in record.linked_providers:
        try:
            company = PartyRef.from_ruc(linked.presence.ruc, linked.presence.business_name)
        except ValueError:
            continue
        links.append(
            PartyLink(
                holder=person,
                company=company,
                link_type=LinkType.SEACE_LINKED_PROVIDER,
                source_name=source_name,
                role=linked.presence.condition,
            )
        )
        links.extend(links_from_seace_provider(linked.record, company, source_name))
    return links


def unique_links(links: list[PartyLink]) -> Iterator[PartyLink]:
    """Elimina repetidos (mismo titular, empresa, tipo y fuente), conservando el primero."""
    seen: set[tuple] = set()
    for link in links:
        key = (
            link.holder.document_type,
            link.holder.document_number,
            link.company.document_type,
            link.company.document_number,
            link.link_type,
            link.source_name,
        )
        if key not in seen:
            seen.add(key)
            yield link
