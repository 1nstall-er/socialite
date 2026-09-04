"""Rate limiting en memoria, acotado, thread-safe y sin dependencias web."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from math import ceil
from threading import RLock
from time import monotonic
from typing import Final

MAXIMO_CLAVES_PREDETERMINADO: Final[int] = 10_000


@dataclass(frozen=True, slots=True)
class DecisionLimite:
    permitido: bool
    restantes: int
    reintentar_en: int


class LimitadorVentanaDeslizante:
    """Cuenta eventos por clave dentro de una ventana temporal exacta.

    El almacenamiento está acotado para que IPs aleatorias no aumenten la
    memoria indefinidamente. La interfaz permite sustituirlo más adelante por
    Redis sin cambiar la lógica de autenticación o verificación.
    """

    def __init__(
        self,
        max_eventos: int,
        ventana_segundos: int,
        max_claves: int = MAXIMO_CLAVES_PREDETERMINADO,
    ) -> None:
        if max_eventos < 1 or ventana_segundos < 1 or max_claves < 1:
            raise ValueError("Los límites deben ser enteros positivos")
        self.max_eventos = max_eventos
        self.ventana_segundos = ventana_segundos
        self.max_claves = max_claves
        self._eventos: dict[str, deque[float]] = {}
        self._lock = RLock()

    def consultar(
        self, clave: str, *, consumir: bool = False, instante: float | None = None
    ) -> DecisionLimite:
        ahora = monotonic() if instante is None else instante
        clave_segura = clave or "desconocido"
        with self._lock:
            eventos = self._eventos.setdefault(clave_segura, deque())
            limite_inferior = ahora - self.ventana_segundos
            while eventos and eventos[0] <= limite_inferior:
                eventos.popleft()

            if len(eventos) >= self.max_eventos:
                espera = max(ceil(self.ventana_segundos - (ahora - eventos[0])), 1)
                return DecisionLimite(False, 0, espera)

            if consumir:
                eventos.append(ahora)
            restantes = max(self.max_eventos - len(eventos), 0)
            self._podar(ahora)
            return DecisionLimite(True, restantes, 0)

    def limpiar(self, clave: str) -> None:
        with self._lock:
            self._eventos.pop(clave or "desconocido", None)

    def _podar(self, ahora: float) -> None:
        if len(self._eventos) <= self.max_claves:
            return
        limite_inferior = ahora - self.ventana_segundos
        expiradas = [
            clave
            for clave, eventos in self._eventos.items()
            if not eventos or eventos[-1] <= limite_inferior
        ]
        for clave in expiradas:
            self._eventos.pop(clave, None)
        if len(self._eventos) > self.max_claves:
            exceso = len(self._eventos) - self.max_claves
            antiguas = sorted(
                self._eventos,
                key=lambda clave: self._eventos[clave][-1]
                if self._eventos[clave]
                else float("-inf"),
            )
            for clave in antiguas[:exceso]:
                self._eventos.pop(clave, None)
