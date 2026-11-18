from app.application.dto.command.get_sunarp_command import GetSunarpCommand
from app.application.dto.result.sunarp_result import SunarpResult
from app.infrastructure.inbound.dto.response.sunarp_response import SunarpResponse


def to_command(oficina: str, area: str, partida: str) -> GetSunarpCommand:
    return GetSunarpCommand(oficina=oficina, area=area, partida=partida)


def to_response(result: SunarpResult) -> SunarpResponse:
    return SunarpResponse.model_validate(result)