from app.application.dto.command.get_sunarp_command import GetSunarpCommand
from app.application.dto.result.sunarp_result import SunarpResult
from app.core.files import build_file_url
from app.infrastructure.inbound.dto.response.sunarp_response import SunarpResponse


def to_command(oficina: str, area: str, partida: str) -> GetSunarpCommand:
    return GetSunarpCommand(oficina=oficina, area=area, partida=partida)


def to_response(result: SunarpResult, base_url: str) -> SunarpResponse:
    response = SunarpResponse.model_validate(result)
    if response.record:
        for seat in response.record.seats:
            for document in seat.documents:
                document.url = build_file_url(document.file_path, base_url)
    return response
