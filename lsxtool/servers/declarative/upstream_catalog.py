"""
Catálogo declarativo de upstreams reutilizables.
Fuente de verdad para IPs, pesos y canary; los .conf se generan desde aquí.
"""

from typing import Optional, List, Literal
from pydantic import BaseModel, Field


# --- Modelos del catálogo ---

UpstreamType = Literal["single", "weighted"]
UpstreamStrategy = Literal["canary", "round_robin"]
ServerRole = Literal["stable", "canary", "primary", "backup"]


class UpstreamServerEntry(BaseModel):
    """Un servidor dentro de un upstream (IP/host + puerto + opcionales)."""
    host: str = Field(..., description="IP o hostname (ej: 127.0.0.1, 192.168.20.234)")
    port: int = Field(..., description="Puerto del servicio")
    weight: Optional[int] = Field(None, description="Peso para balanceo (weighted)")
    role: Optional[ServerRole] = Field(None, description="stable, canary, primary, backup")


class UpstreamHealthcheck(BaseModel):
    """Healthcheck opcional para el upstream."""
    path: Optional[str] = Field(None, description="Ruta de health (ej: /health)")
    interval: Optional[str] = Field(None, description="Intervalo (ej: 5s)")


class CanaryConfig(BaseModel):
    """Configuración de canary progresivo."""
    enabled: bool = Field(False, description="Canary habilitado")
    current_weight: int = Field(10, description="Peso actual del canary (%)")
    step: int = Field(10, description="Incremento por promote (%)")
    max: int = Field(50, description="Peso máximo del canary (%)")


class UpstreamCatalogDef(BaseModel):
    """
    Definición de un upstream en el catálogo (.lsxtool/upstreams/*.yaml).
    Reutilizable por varios dominios vía upstream_ref.
    """
    name: str = Field(..., description="Nombre lógico (ej: api_identity_dev)")
    type: UpstreamType = Field("single", description="single | weighted")
    protocol: str = Field("http", description="http o https")
    strategy: Optional[UpstreamStrategy] = Field(None, description="canary | round_robin")
    servers: List[UpstreamServerEntry] = Field(..., min_length=1)
    healthcheck: Optional[UpstreamHealthcheck] = Field(None)
    canary: Optional[CanaryConfig] = Field(None)

    class Config:
        use_enum_values = True
