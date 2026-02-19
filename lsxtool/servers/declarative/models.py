"""
Modelos de datos para el sistema declarativo
Usa Pydantic para validación y serialización
"""

from typing import Optional, List, Dict, Any, Literal
from pathlib import Path
from pydantic import BaseModel, Field, validator
from enum import Enum


class DomainType(str, Enum):
    """Tipo de dominio"""
    ROOT = "root"
    SUBDOMAIN = "subdomain"


class ServerWebType(str, Enum):
    """Tipo de servidor web / edge (quién atiende el dominio, escucha el puerto, genera el .conf)"""
    NGINX = "nginx"
    APACHE = "apache"
    TRAEFIK = "traefik"
    CADDY = "caddy"


# Alias para compatibilidad con código que aún use BackendType
BackendType = ServerWebType


class TechType(str, Enum):
    """Tipo de tecnología runtime"""
    NODE = "node"
    PHP = "php"
    PYTHON = "python"


# TechProvider y TechManager son strings, no Enums estrictos
# para permitir extensibilidad
TechProvider = str  # volta, nvm, asdf, system, container, phpbrew, pyenv
TechManager = str   # npm, yarn, pnpm, bun, composer, pip, poetry


class Environment(str, Enum):
    """Ambiente de despliegue"""
    DEV = "dev"
    QA = "qa"
    PROD = "prod"


class ServiceType(str, Enum):
    """Tipo de servicio"""
    WEB = "web"
    API = "api"
    ADMIN = "admin"
    STATIC = "static"


class UpstreamConfig(BaseModel):
    """Configuración de upstream"""
    service_type: ServiceType
    tech: TechType
    tech_version: str
    tech_provider: str = Field(..., description="Provider de tecnología (volta, nvm, asdf, system, container, etc.)")
    tech_manager: str = Field(..., description="Gestor de paquetes (npm, yarn, pnpm, bun, composer, pip, poetry)")
    port: int = Field(..., description="Puerto del servicio backend")
    
    class Config:
        use_enum_values = True


ServerWebMode = Literal["proxy", "static", "php-fpm"]


class ServerWebConfig(BaseModel):
    """
    Configuración del servidor web / edge que atiende el dominio.
    Quién escucha el puerto, define upstream/proxy/root y genera el .conf.
    """
    type: ServerWebType = Field(..., alias="type", description="nginx | apache | caddy | traefik")
    version: Optional[str] = Field(None, description="Versión del servidor web (ej: 1.26)")
    mode: Optional[ServerWebMode] = Field(None, description="proxy | static | php-fpm")
    root: Optional[str] = Field(None, description="DocumentRoot o root path")
    upstream_ref: Optional[str] = Field(
        None,
        description="Referencia a upstream del catálogo. Si existe, no se usa upstream inline.",
    )
    upstream: Optional[UpstreamConfig] = Field(
        None,
        description="Configuración de upstream inline (solo si no hay upstream_ref)",
    )
    listen_port: Optional[int] = Field(None, description="Puerto de escucha del servidor web")

    class Config:
        use_enum_values = True
        populate_by_name = True


# Alias para compatibilidad con código que aún use BackendConfig
BackendConfig = ServerWebConfig


class DomainConfig(BaseModel):
    """Configuración completa de un dominio"""
    domain: str = Field(..., description="Dominio completo (ej: dev-identity.lunarsystemx.com)")
    type: DomainType = Field(..., description="Tipo de dominio (root o subdomain)")
    slug: str = Field(..., description="Slug del dominio (ej: identity)")
    environment: Environment
    provider: str = Field(..., description="Provider (LSX, STIC, EXTERNAL)")
    server: Optional[str] = Field(None, description="Servidor físico donde corre (ej: srvecnom-dev)")
    server_web: ServerWebConfig = Field(..., alias="server_web", description="Servidor web que atiende el dominio")
    owner: Optional[str] = Field(None, description="Equipo responsable (mapea a grupo del sistema)")
    technical_user: Optional[str] = Field(None, description="Usuario técnico para ownership de FS (ej: michael.carrillo)")
    description: Optional[str] = Field(None, description="Descripción del servicio")
    
    @validator("type", pre=True)
    def infer_domain_type(cls, v, values):
        """Infiere el tipo de dominio si no está especificado"""
        if isinstance(v, str) and v in ["root", "subdomain"]:
            return v
        if "domain" in values:
            domain = values["domain"]
            # 2+ puntos → subdomain, 1 punto → root
            return DomainType.SUBDOMAIN if domain.count(".") >= 2 else DomainType.ROOT
        return v
    
    @validator("slug", pre=True)
    def infer_slug(cls, v, values):
        """Infiere el slug si no está especificado"""
        if v:
            return v
        if "domain" in values:
            domain = values["domain"]
            # Remover prefijos de ambiente
            domain_clean = domain.replace("dev-", "").replace("qa-", "").replace("prod-", "")
            # Tomar primera parte antes del primer punto
            return domain_clean.split(".")[0]
        return v
    
    class Config:
        use_enum_values = True


class ProviderConfig(BaseModel):
    """Configuración de un provider"""
    name: str = Field(..., description="Nombre del provider (LSX, STIC, etc.)")
    description: Optional[str] = None
    defaults: Optional[Dict[str, Any]] = Field(None, description="Valores por defecto del provider")


class ServerConfig(BaseModel):
    """Configuración de un servidor físico"""
    name: str = Field(..., description="Nombre del servidor (ej: srvecnom-dev)")
    hostname: Optional[str] = Field(None, description="Hostname o IP")
    environment: Environment
    provider: str
    description: Optional[str] = None


class ServiceConfig(BaseModel):
    """Configuración de un servicio (puede tener múltiples dominios)"""
    name: str = Field(..., description="Nombre del servicio (ej: identity-api)")
    service_type: ServiceType
    tech: TechType
    tech_version: str
    tech_provider: TechProvider
    tech_manager: TechManager
    domains: List[str] = Field(..., description="Lista de dominios que pertenecen a este servicio")
    description: Optional[str] = None
    
    class Config:
        use_enum_values = True


class GlobalsConfig(BaseModel):
    """Configuración global y defaults"""
    defaults: Dict[str, Any] = Field(default_factory=dict, description="Valores por defecto globales")
    conventions: Optional[Dict[str, Any]] = Field(None, description="Convenciones de naming, paths, etc.")


class RootOrchestrator(BaseModel):
    """Orquestador raíz (lsx.yaml)"""
    version: int = Field(1, description="Versión del esquema")
    providers: List[str] = Field(default_factory=list, description="Rutas a archivos de providers")
    servers: List[str] = Field(default_factory=list, description="Rutas a archivos de servers")
    domains: List[str] = Field(default_factory=list, description="Rutas a archivos de domains")
    services: List[str] = Field(default_factory=list, description="Rutas a archivos de services")
    defaults: Optional[Dict[str, Any]] = Field(None, description="Defaults globales (puede estar en globals.yaml)")
