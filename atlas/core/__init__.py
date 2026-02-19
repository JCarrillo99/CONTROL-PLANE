"""
Core: lógica de negocio pura.

ENFORCEMENT (arquitectura limpia):
- Este paquete NO debe importar: atlas.cli, atlas.providers.* (implementaciones),
  ni módulos que accedan al filesystem real (salvo resolver que solo devuelve Path).
- Permitido: typing, pathlib.Path, pydantic, atlas.core.* (errors, runtime, infra/contracts).
- Los providers y la CLI importan desde core; nunca al revés.
"""

from atlas.core.errors import AtlasError, ValidationError, ConfigError

__all__ = ["AtlasError", "ValidationError", "ConfigError"]
