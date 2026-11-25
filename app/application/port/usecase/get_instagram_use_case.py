from abc import ABC, abstractmethod

from app.application.dto.command.get_instagram_command import GetInstagramCommand
from app.application.dto.result.instagram_result import InstagramResult


class GetInstagramUseCase(ABC):
    @abstractmethod
    async def execute(self, command: GetInstagramCommand) -> InstagramResult: ...
