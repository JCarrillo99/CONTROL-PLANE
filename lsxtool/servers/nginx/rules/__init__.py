"""
Sistema de reglas de validación para Nginx
Cada regla valida un aspecto específico de la configuración
"""

from .base import ValidationRule, ValidationResult, Severity, FixCapability
from .meta import MetaValidationRule
from .domain import DomainValidationRule
from .backend import BackendValidationRule
from .upstream import UpstreamValidationRule
from .logs import LogsValidationRule
from .ports import PortsValidationRule
from .provider import ProviderValidationRule
from .versions import VersionsValidationRule
from .tech_metadata import TechMetadataValidationRule

__all__ = [
    "ValidationRule",
    "ValidationResult",
    "Severity",
    "FixCapability",
    "MetaValidationRule",
    "DomainValidationRule",
    "BackendValidationRule",
    "UpstreamValidationRule",
    "LogsValidationRule",
    "PortsValidationRule",
    "ProviderValidationRule",
    "VersionsValidationRule",
    "TechMetadataValidationRule",
]

# Registro de todas las reglas disponibles
ALL_RULES = [
    MetaValidationRule,
    DomainValidationRule,
    BackendValidationRule,
    UpstreamValidationRule,
    LogsValidationRule,
    PortsValidationRule,
    ProviderValidationRule,
    VersionsValidationRule,
    TechMetadataValidationRule,
]
