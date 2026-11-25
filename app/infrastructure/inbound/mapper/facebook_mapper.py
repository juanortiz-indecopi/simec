from pathlib import Path

from app.application.dto.command.get_facebook_page_command import GetFacebookPageCommand
from app.application.dto.result.facebook_page_result import FacebookPageResult
from app.core.files import build_file_url
from app.infrastructure.inbound.dto.response.facebook_response import FacebookPageQueryResponse
from app.infrastructure.inbound.mapper.audit_mapper import to_audit_responses


def to_command(page: str, ruc: str | None = None, refresh: bool = False) -> GetFacebookPageCommand:
    return GetFacebookPageCommand(page=page, ruc=ruc, refresh=refresh)


def to_response(result: FacebookPageResult, base_url: str) -> FacebookPageQueryResponse:
    response = FacebookPageQueryResponse.model_validate(result)
    response.audit_entries = to_audit_responses(result.audit_entries, result.data_origins)
    page = response.page
    # El archivo pudo borrarse después de guardar la página: no se publica un enlace roto.
    if page and page.photo_path and Path(page.photo_path).is_file():
        page.photo_url = build_file_url(page.photo_path, base_url)
    return response
