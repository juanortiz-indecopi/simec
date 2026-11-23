from app.application.dto.command.get_sunarp_command import GetSunarpCommand
from app.application.dto.result.sunarp_result import SunarpResult
from app.core.files import build_file_url
from app.infrastructure.inbound.dto.response.sunarp_response import SunarpResponse
from app.infrastructure.inbound.mapper.audit_mapper import to_audit_responses


def to_command(oficina: str, area: str, partida: str, refresh: bool = False) -> GetSunarpCommand:
    return GetSunarpCommand(oficina=oficina, area=area, partida=partida, refresh=refresh)


def to_response(result: SunarpResult, base_url: str) -> SunarpResponse:
    response = SunarpResponse.model_validate(result)
    response.audit_entries = to_audit_responses(result.audit_entries, result.data_origins)
    if response.record:
        for seat in response.record.seats:
            for document in seat.documents:
                document.url = build_file_url(document.file_path, base_url)
    return response
