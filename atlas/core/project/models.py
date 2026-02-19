"""
Modelos de datos del Control Plane (agnósticos de interfaz y filesystem).

Copiados/adaptados del sistema declarativo para que el core no dependa de lsxtool.
"""

from enum import Enum
from typing import Any, Dict, List, Literal, Optional

try:
    from pydantic import BaseModel, Field, validator
except ImportError:
    BaseModel = object  # type: ignore
    Field = None  # type: ignore
    validator = None  # type: ignore


class DomainType(str, Enum):
    ROOT = "root"
    SUBDOMAIN = "subdomain"


class ServerWebType(str, Enum):
    NGINX = "nginx"
    APACHE = "apache"
    TRAEFIK = "traefik"
    CADDY = "caddy"


class TechType(str, Enum):
    NODE = "node"
    PHP = "php"
    PYTHON = "python"


class Environment(str, Enum):
    DEV = "dev"
    QA = "qa"
    PROD = "prod"


class ServiceType(str, Enum):
    WEB = "web"
    API = "api"
    ADMIN = "admin"
    STATIC = "static"


TechProvider = str
TechManager = str

ServerWebMode = Literal["proxy", "static", "php-fpm"]


if BaseModel is not object and Field is not None:

    class UpstreamConfig(BaseModel):
        service_type: ServiceType
        tech: TechType
        tech_version: str
        tech_provider: str = Field(..., description="Provider de tecnología")
        tech_manager: str = Field(..., description="Gestor de paquetes")
        port: int = Field(..., description="Puerto del servicio backend")

        class Config:
            use_enum_values = True

    class ServerWebConfig(BaseModel):
        type: ServerWebType = Field(..., alias="type")
        version: Optional[str] = None
        mode: Optional[ServerWebMode] = None
        root: Optional[str] = None
        upstream_ref: Optional[str] = None
        upstream: Optional["UpstreamConfig"] = None
        listen_port: Optional[int] = None

        class Config:
            use_enum_values = True
            populate_by_name = True

    class DomainConfig(BaseModel):
        domain: str = Field(..., description="Dominio completo")
        type: DomainType = Field(..., description="root o subdomain")
        slug: str = Field(..., description="Slug del dominio")
        environment: Environment = Field(...)
        provider: str = Field(..., description="Provider")
        server: Optional[str] = None
        server_web: ServerWebConfig = Field(..., alias="server_web")
        owner: Optional[str] = None
        technical_user: Optional[str] = None
        description: Optional[str] = None

        class Config:
            use_enum_values = True
            populate_by_name = True

    class ProviderConfig(BaseModel):
        name: str = Field(...)
        description: Optional[str] = None
        defaults: Optional[Dict[str, Any]] = None

    class ServerConfig(BaseModel):
        name: str = Field(...)
        hostname: Optional[str] = None
        environment: Environment = Field(...)
        provider: str = Field(...)
        description: Optional[str] = None

    class ServiceConfig(BaseModel):
        name: str = Field(...)
        service_type: ServiceType = Field(...)
        tech: TechType = Field(...)
        tech_version: str = Field(...)
        tech_provider: TechProvider = Field(...)
        tech_manager: TechManager = Field(...)
        domains: List[str] = Field(...)
        description: Optional[str] = None

        class Config:
            use_enum_values = True

    class GlobalsConfig(BaseModel):
        defaults: Dict[str, Any] = Field(default_factory=dict)
        conventions: Optional[Dict[str, Any]] = None

    class RootOrchestrator(BaseModel):
        version: int = Field(1, description="Versión del esquema")
        providers: List[str] = Field(default_factory=list)
        servers: List[str] = Field(default_factory=list)
        domains: List[str] = Field(default_factory=list)
        services: List[str] = Field(default_factory=list)
        defaults: Optional[Dict[str, Any]] = None

else:
    # Sin Pydantic: tipos mínimos para no romper imports
    UpstreamConfig = None  # type: ignore
    ServerWebConfig = None  # type: ignore
    DomainConfig = None  # type: ignore
    ProviderConfig = None  # type: ignore
    ServerConfig = None  # type: ignore
    ServiceConfig = None  # type: ignore
    GlobalsConfig = None  # type: ignore
    RootOrchestrator = None  # type: ignore
