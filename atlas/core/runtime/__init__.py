"""
Runtime: resolución de rutas de estado y contratos de estado.

El estado real NUNCA vive dentro del repo; se escribe en /var/lib/lsx/atlas/.
"""

from atlas.core.runtime.resolver import state_root, project_base

__all__ = ["state_root", "project_base"]
