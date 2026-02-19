"""
Base opcional para providers: implementación por defecto de métodos comunes.

Los providers pueden heredar de aquí o implementar solo el contrato (Protocol).
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from atlas.core.runtime.state import StateDiff
from atlas.core.infra.contracts import PlanResult


class BaseProvider:
    """Base opcional para providers; no obligatorio usar herencia."""

    name: str = "base"

    def plan(self, base: Path, desired: Dict[str, Any]) -> PlanResult:
        """Por defecto: sin acciones."""
        return PlanResult(actions=[], diffs=[], summary="No plan defined")

    def apply(self, base: Path, desired: Dict[str, Any]) -> bool:
        """Por defecto: no aplica nada."""
        return False

    def detect_drift(self, base: Path, resource_id: Optional[str] = None) -> List[StateDiff]:
        """Por defecto: sin drift."""
        return []
