"""
Detección de drift (diferencias entre estado deseado y real).

El core solo define la noción de "diff"; la obtención del estado real
(leyendo .conf, YAML, etc.) la implementan los providers mediante
el contrato DriftDetector.
"""

from typing import Any, Dict, List

from atlas.core.runtime.state import StateDiff


def merge_diffs(diff_lists: List[List[StateDiff]]) -> List[StateDiff]:
    """Combina listas de diffs de varios providers y devuelve una sola lista."""
    out: List[StateDiff] = []
    seen: set = set()
    for lst in diff_lists:
        for d in lst:
            key = (d.resource_id, d.field)
            if key not in seen:
                seen.add(key)
                out.append(d)
    return out
