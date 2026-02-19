"""
Contratos que deben implementar los providers de infraestructura.

El core solo define interfaces; la implementación vive en atlas/providers/*.
"""

from typing import Any, Dict, List, Optional, Protocol
from pathlib import Path

from atlas.core.runtime.state import StateDiff


class PlanResult:
    """Resultado de un plan (qué se aplicaría) sin ejecutar."""
    def __init__(
        self,
        actions: List[str],
        diffs: List[StateDiff],
        summary: str = ""
    ):
        self.actions = actions
        self.diffs = diffs
        self.summary = summary


class ProviderContract(Protocol):
    """
    Contrato mínimo de un provider (nginx, apache, traefik, dns, etc.).
    No ejecuta lógica directa; expone plan/apply detrás de interfaces.
    """
    @property
    def name(self) -> str:
        """Identificador del provider (ej: nginx, apache)."""
        ...

    def plan(self, base: Path, desired: Dict[str, Any]) -> PlanResult:
        """Calcula qué cambios se aplicarían (sin ejecutar)."""
        ...

    def apply(self, base: Path, desired: Dict[str, Any]) -> bool:
        """Aplica el estado deseado. Devuelve True si éxito."""
        ...

    def detect_drift(self, base: Path, resource_id: Optional[str] = None) -> List[StateDiff]:
        """Detecta diferencias entre estado deseado y real."""
        ...
