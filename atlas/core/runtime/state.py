"""
Contratos de estado (State): lectura/escritura abstracta.

El core NO implementa lectura/escritura real de .conf o YAML;
eso lo hacen los providers. Aquí solo se definen interfaces/protocolos.
"""

from typing import Any, Dict, List, Optional, Protocol
from pathlib import Path


class StateDiff:
    """Diferencia entre estado deseado y real (agnóstico de provider)."""
    def __init__(
        self,
        resource_id: str,
        field: str,
        desired: Any,
        actual: Any,
        severity: str = "warning"
    ):
        self.resource_id = resource_id
        self.field = field
        self.desired = desired
        self.actual = actual
        self.severity = severity  # "error", "warning", "info"


class StateReader(Protocol):
    """Protocolo: quien lee estado real (p. ej. nginx .conf)."""
    def read_current(self, base: Path, resource_id: Optional[str] = None) -> Dict[str, Any]:
        ...


class StateWriter(Protocol):
    """Protocolo: quien escribe estado (p. ej. genera .conf)."""
    def write_desired(self, base: Path, desired: Dict[str, Any]) -> bool:
        ...


class DriftDetector(Protocol):
    """Protocolo: detecta drift entre deseado y real."""
    def detect_drift(
        self,
        base: Path,
        resource_id: Optional[str] = None
    ) -> List[StateDiff]:
        ...
