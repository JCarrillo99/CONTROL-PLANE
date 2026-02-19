"""
Planificación: genera un plan de cambios (qué aplicar) sin ejecutar.

Lógica pura: entrada = estado deseado + estado actual (estructuras);
salida = lista de acciones. La ejecución la hacen los providers.
"""

from typing import Any, Dict, List

from atlas.core.runtime.state import StateDiff


def plan_from_diffs(diffs: List[StateDiff]) -> List[str]:
    """
    Convierte una lista de StateDiff en acciones legibles (para mostrar en CLI/API).
    No ejecuta nada.
    """
    actions: List[str] = []
    for d in diffs:
        if d.severity == "error":
            actions.append(f"Crear/actualizar {d.resource_id}: {d.field} = {d.desired}")
        elif d.desired != d.actual:
            actions.append(f"Actualizar {d.resource_id}.{d.field}: {d.actual} → {d.desired}")
    return actions
