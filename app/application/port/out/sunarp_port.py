from abc import ABC, abstractmethod
from typing import Any

class SunarpPort(ABC):
    @property
    @abstractmethod
    def source_name(self) -> str: ...

    @abstractmethod
    async def extract(self, oficina: str, area: str, partida: str) -> dict[str, Any]: ...