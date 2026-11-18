from abc import ABC, abstractmethod

from app.application.dto.command.get_sunarp_command import GetSunarpCommand
from app.application.dto.result.sunarp_result import SunarpResult


class GetSunarpUseCase(ABC):
    @abstractmethod
    async def execute(self, command: GetSunarpCommand) -> SunarpResult: ...