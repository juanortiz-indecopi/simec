import threading
import time
from typing import Final

MIN_INTERVAL_S: Final = 10.0
BLOCK_COOLDOWN_S: Final = 15 * 60.0


class Pace:
    """Espacia las visitas y las suspende tras un bloqueo (compartido entre hilos y loops)."""

    def __init__(
        self, min_interval_s: float = MIN_INTERVAL_S, cooldown_s: float = BLOCK_COOLDOWN_S
    ) -> None:
        self._min_interval_s = min_interval_s
        self._cooldown_s = cooldown_s
        self._lock = threading.Lock()
        self._next_visit = 0.0
        self._blocked_until = 0.0

    def reserve(self) -> float:
        """Reserva turno y devuelve los segundos que hay que esperar."""
        with self._lock:
            now = time.monotonic()
            visit = max(now, self._next_visit)
            self._next_visit = visit + self._min_interval_s
            return visit - now

    def blocked_for(self) -> float:
        with self._lock:
            return max(0.0, self._blocked_until - time.monotonic())

    def block(self) -> None:
        with self._lock:
            self._blocked_until = time.monotonic() + self._cooldown_s
