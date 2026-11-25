from abc import ABC, abstractmethod

from app.application.dto.command.get_news_command import GetNewsCommand
from app.application.dto.result.news_result import NewsResult


class GetNewsUseCase(ABC):
    @abstractmethod
    async def execute(self, command: GetNewsCommand) -> NewsResult: ...
