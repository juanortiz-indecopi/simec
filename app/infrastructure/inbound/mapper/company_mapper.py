from app.infrastructure.inbound.dto.response.company_response import CompanyResponse
from app.infrastructure.inbound.mapper.audit_mapper import to_audit_responses
from app.application.dto.command.get_company_command import GetCompanyCommand
from app.application.dto.result.company_result import CompanyResult


def to_command(ruc: str, refresh: bool = False) -> GetCompanyCommand:
    return GetCompanyCommand(ruc=ruc, refresh=refresh)


def to_response(result: CompanyResult) -> CompanyResponse:
    response = CompanyResponse.model_validate(result)
    response.audit_entries = to_audit_responses(result.audit_entries, result.data_origins)
    return response
