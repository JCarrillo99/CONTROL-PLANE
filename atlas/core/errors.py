"""
Errores del Control Plane.

El core solo define excepciones; las capas (CLI/API) se encargan del formato de salida.
"""


class AtlasError(Exception):
    """Error base de ATLAS."""
    pass


class ValidationError(AtlasError):
    """Error de validación de configuración o modelos."""
    pass


class ConfigError(AtlasError):
    """Error de configuración (archivo faltante, formato inválido)."""
    pass


class ProviderError(AtlasError):
    """Error delegado desde un provider (nginx, apache, etc.)."""
    pass
