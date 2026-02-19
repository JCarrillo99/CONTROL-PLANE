"""
Project: modelos, validación, planificación y detección de drift.

Lógica pura; sin I/O ni dependencias de CLI o providers.
"""

from atlas.core.project import models
from atlas.core.project.validator import validate_domain_slug, validate_environment, validate_desired_config
from atlas.core.project.planner import plan_from_diffs
from atlas.core.project.detector import merge_diffs

# Re-exportar modelos solo si Pydantic está disponible (no None)
DomainConfig = getattr(models, "DomainConfig", None)
Environment = getattr(models, "Environment", None)
ServerWebType = getattr(models, "ServerWebType", None)
ServiceType = getattr(models, "ServiceType", None)
TechType = getattr(models, "TechType", None)
RootOrchestrator = getattr(models, "RootOrchestrator", None)

__all__ = [
    "DomainConfig",
    "Environment",
    "ServerWebType",
    "ServiceType",
    "TechType",
    "RootOrchestrator",
    "validate_domain_slug",
    "validate_environment",
    "validate_desired_config",
    "plan_from_diffs",
    "merge_diffs",
]
