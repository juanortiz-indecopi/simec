from abc import ABC, abstractmethod

from app.application.dto.command.get_facebook_page_command import GetFacebookPageCommand
from app.application.dto.result.facebook_page_result import FacebookPageResult


class GetFacebookPageUseCase(ABC):
    @abstractmethod
    async def execute(self, command: GetFacebookPageCommand) -> FacebookPageResult: ...
