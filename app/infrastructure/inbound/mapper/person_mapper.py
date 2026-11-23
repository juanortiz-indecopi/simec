from app.infrastructure.inbound.dto.response.person_response import PersonResponse
from app.infrastructure.inbound.mapper.audit_mapper import to_audit_responses
from app.application.dto.command.get_person_command import GetPersonCommand
from app.application.dto.result.person_result import PersonResult


def to_command(dni: str, refresh: bool = False) -> GetPersonCommand:
    return GetPersonCommand(dni=dni, refresh=refresh)


def to_response(result: PersonResult) -> PersonResponse:
    response = PersonResponse.model_validate(result)
    response.audit_entries = to_audit_responses(result.audit_entries, result.data_origins)
    return response
