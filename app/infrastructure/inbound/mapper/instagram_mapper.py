from pathlib import Path

from app.application.dto.command.get_instagram_command import GetInstagramCommand
from app.application.dto.result.instagram_result import InstagramResult
from app.core.files import build_file_url
from app.infrastructure.inbound.dto.response.instagram_response import InstagramResponse
from app.infrastructure.inbound.mapper.audit_mapper import to_audit_responses


def to_command(username: str, refresh: bool = False) -> GetInstagramCommand:
    return GetInstagramCommand(username=username, refresh=refresh)


def to_response(result: InstagramResult, base_url: str) -> InstagramResponse:
    response = InstagramResponse.model_validate(result)
    response.audit_entries = to_audit_responses(result.audit_entries, result.data_origins)
    profile = response.profile
    # El archivo pudo borrarse después de guardar el perfil: no se publica un enlace roto.
    if profile and profile.photo_path and Path(profile.photo_path).is_file():
        profile.photo_url = build_file_url(profile.photo_path, base_url)
    return response
