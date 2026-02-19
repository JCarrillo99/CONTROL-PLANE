"""
Modelos v2 para el sistema declarativo (formato obligatorio).
Separa frontend, upstream, access_type, canonical_domain.
Soporta routes como lista con name, y upstreams con múltiples nodos para canary/weighted.

Tipos de routing importados de routing_domain (estrategia vs algoritmo).
"""

from typing import Optional, List, Dict, Any, Literal, Union
from pydantic import BaseModel, Field, model_validator

from .models import Environment, ServerWebType
from .routing_domain import (
    Role,
    AccessType,
    UriStrategy,
    RoutingStrategy,
    RoutingAlgorithm,
    CanaryMode,
    validate_routing_combination,
)


# --- URI Transform ---

class UriTransformConfig(BaseModel):
    """
    Transformación URI: cómo traducir path público → path upstream.
    - public: path en el location de NGINX (ej: /api/identity/)
    - upstream: path real que espera la app (ej: /)
    - strategy: strip (rewrite) | passthrough (proxy_pass con URI)
    """
    public: str = Field(..., description="Path público en NGINX location")
    upstream: str = Field(..., description="Path real en la aplicación upstream")
    strategy: UriStrategy = Field("strip", description="strip | passthrough")


# --- Root Config ---

class RootConfig(BaseModel):
    """Root declarado para ownership y permisos (path, owner, technical_user)."""
    path: str = Field(..., description="Ruta en disco (ej: /mnt/d/www/.../frontend)")
    owner: str = Field(..., description="Grupo responsable (ej: equipo-identity)")
    technical_user: str = Field("michael.carrillo", description="Usuario técnico (default: michael.carrillo)")


# --- Route Config (ahora con name explícito) ---

class RouteConfig(BaseModel):
    """
    Ruta con nombre explícito → tipo proxy, upstream_ref y transformación URI.
    """
    name: str = Field(..., description="Nombre único de la ruta (ej: api_identity, frontend_php)")
    type: Literal["proxy"] = "proxy"
    upstream_ref: str = Field(..., description="Referencia al upstream (ej: api__identity)")
    uri: UriTransformConfig = Field(..., description="Transformación URI (public, upstream, strategy)")


# --- Server Web Config ---

class ServerWebConfigV2(BaseModel):
    """Quién atiende el dominio (solo nginx/apache/caddy; NO backend)."""
    type: str = Field(..., alias="type", description="nginx | apache | caddy")
    version: Optional[str] = None

    class Config:
        populate_by_name = True


# --- Frontend Domain Config ---

class FrontendDomainConfig(BaseModel):
    """
    Dominio frontend (raíz que recibe tráfico).
    Puede ser compuesto: / + /api/identity/ + /api/demo/ → múltiples upstreams.
    routes ahora es una LISTA con name explícito.
    """
    domain: str = Field(..., description="Dominio canónico (ej: dev-identity.lunarsystemx.com)")
    role: Literal["frontend"] = "frontend"
    environment: str = Field("dev", description="dev | qa | prod")
    provider: str = Field(..., description="Provider (ej: lunarsystemx)")

    server_web: ServerWebConfigV2 = Field(..., alias="server_web")

    root: Optional[RootConfig] = Field(None, description="Root declarado para ownership; puede comentarse en nginx si solo proxy")

    routes: List[RouteConfig] = Field(
        default_factory=list,
        description='Lista de routes: [{ name, type, upstream_ref, uri }]',
    )

    class Config:
        populate_by_name = True


# --- Upstream (formato nuevo con soporte canary/multi-node) ---

class UpstreamIdentityConfig(BaseModel):
    """Identidad lógica del upstream (para agrupación y discovery)."""
    slug: str = Field(..., description="Slug único (ej: identity, demo)")
    domain_group: Optional[str] = Field(None, description="Grupo de dominio (ej: identity, demo)")


class UpstreamDomainsConfig(BaseModel):
    canonical: Optional[str] = Field(None, description="Dominio lógico estable (ej: api.identity.lunarsystemx.com)")


class UpstreamExposureConfig(BaseModel):
    access_type: AccessType = Field("internal", description="internal | external | mixed")


class UpstreamTechConfig(BaseModel):
    """Tech stack de un nodo upstream."""
    language: str = Field(..., description="node | php | python")
    version: str = Field(..., description='ej: "20", "7.2"')
    provider: Optional[str] = Field("system", description="volta | nvm | asdf | system | container")
    manager: Optional[str] = Field(None, description="npm | yarn | pnpm | composer | pip")


class UpstreamRuntimeConfig(BaseModel):
    """Runtime de un nodo upstream."""
    host: str = Field(..., description="IP o hostname (ej: 192.168.20.234)")
    port: int = Field(..., description="Puerto del servicio")


class UpstreamCanaryConfig(BaseModel):
    """
    Config canary (solo si strategy=canary).
    base_weight + canary_weight = 100 (% de tráfico a cada grupo).
    stickiness: none|request|ip|cookie|header. Si cookie/header → sticky_key.
    """
    mode: CanaryMode = Field("percentage", description="Deprecado: usar stickiness. percentage|header|cookie")
    stickiness: Optional[Literal["none", "request", "ip", "cookie", "header"]] = Field(
        None, description="Persistencia: none=cada request, request=$request_id, ip=$remote_addr, cookie/header=key"
    )
    sticky_key: Optional[str] = Field(None, description="Cookie o header name si stickiness=cookie|header (ej: lsx_demo_canary)")

    @model_validator(mode="before")
    @classmethod
    def coerce_weighted_to_percentage(cls, v: Any) -> Any:
        """Retrocompat: weighted → percentage."""
        if isinstance(v, dict) and v.get("mode") == "weighted":
            v = {**v, "mode": "percentage"}
        return v

    base_weight: int = Field(90, description="% de tráfico a la versión estable (base_weight + canary_weight = 100)")
    canary_weight: int = Field(10, description="% de tráfico a la versión experimental")
    header: Optional[str] = Field(None, description="Header name (retrocompat, preferir sticky_key con stickiness=header)")
    cookie: Optional[str] = Field(None, description="Cookie name (retrocompat, preferir sticky_key con stickiness=cookie)")


class UpstreamRoutingConfig(BaseModel):
    """
    Estrategia (intención) + algoritmo (mecánica) de routing.
    Validado: combinaciones strategy+algorithm deben ser permitidas.
    Retrocompat: strategy "weighted" en YAML → strategy=simple, algorithm=weighted.
    """
    strategy: RoutingStrategy = Field("simple", description="simple | canary | failover | blue_green | mirror")
    algorithm: Optional[RoutingAlgorithm] = Field(None, description="round_robin | least_conn | ip_hash | hash_uri | weighted")
    canary: Optional[UpstreamCanaryConfig] = Field(None, description="Config canary (si strategy=canary)")

    @model_validator(mode="before")
    @classmethod
    def coerce_weighted_strategy(cls, v: Any) -> Any:
        """Retrocompat: strategy 'weighted' → simple + algorithm weighted."""
        if isinstance(v, dict) and v.get("strategy") == "weighted":
            v = {**v, "strategy": "simple", "algorithm": v.get("algorithm") or "weighted"}
        return v

    @model_validator(mode="after")
    def validate_strategy_algorithm(self):
        """Evita combinaciones inválidas (ej. canary+ip_hash, blue_green+round_robin)."""
        valid, err = validate_routing_combination(
            self.strategy,
            self.algorithm,
            self.canary.mode if self.canary else None,
        )
        if not valid:
            raise ValueError(err)
        return self


class UpstreamObservabilityMetricsConfig(BaseModel):
    enabled: bool = Field(True, description="Habilitar métricas")
    per_node: bool = Field(False, description="Métricas por nodo individual")


class UpstreamObservabilityConfig(BaseModel):
    """Observabilidad del upstream."""
    metrics: Optional[UpstreamObservabilityMetricsConfig] = None


NodeGroup = Literal["base", "canary"]


class UpstreamNodeConfig(BaseModel):
    """
    Nodo individual en un upstream.
    - Simple: weight es peso directo (suma total 100).
    - Canary: group=base|canary, weight es relativo DENTRO del grupo.
      Peso efectivo = group_weight * (node_weight / sum_group_weights).
    """
    name: str = Field(..., description="Nombre del nodo (ej: demo_php_72)")
    weight: int = Field(100, description="Peso: directo (simple) o relativo dentro del grupo (canary)")
    group: Optional[NodeGroup] = Field(None, description="base | canary (solo si strategy=canary)")
    backup: bool = Field(False, description="Es nodo backup")
    down: bool = Field(False, description="Nodo marcado como down")
    runtime: UpstreamRuntimeConfig = Field(..., description="host + port")
    tech: Optional[UpstreamTechConfig] = Field(None, description="Tech stack del nodo")


class UpstreamDefConfig(BaseModel):
    """
    Bloque upstream dentro del YAML de upstream.
    Soporta:
    - Simple: un solo nodo (retrocompatible con runtime/tech a nivel raíz)
    - Multi-node: lista de nodes[] con weights para canary/weighted
    """
    name: str = Field(..., description="Nombre lógico (ej: api__identity)")
    service_type: Literal["api", "frontend", "admin", "static"] = "api"

    identity: Optional[UpstreamIdentityConfig] = Field(None, description="Identidad lógica")
    domains: Optional[UpstreamDomainsConfig] = None
    exposure: Optional[UpstreamExposureConfig] = None

    routing: Optional[UpstreamRoutingConfig] = Field(None, description="Estrategia de routing")
    observability: Optional[UpstreamObservabilityConfig] = Field(None, description="Observabilidad")

    # Para multi-node (canary, weighted, etc.)
    nodes: Optional[List[UpstreamNodeConfig]] = Field(None, description="Lista de nodos (para canary/weighted)")

    # Retrocompatibilidad: runtime/tech a nivel raíz para upstream simple (un solo nodo)
    runtime: Optional[UpstreamRuntimeConfig] = Field(None, description="host + port (retrocompat: un solo nodo)")
    tech: Optional[UpstreamTechConfig] = Field(None, description="Tech stack (retrocompat: un solo nodo)")

    @model_validator(mode="after")
    def validate_nodes_or_runtime(self):
        """Debe tener nodes[] o runtime (retrocompat), no ambos vacíos."""
        if not self.nodes and not self.runtime:
            raise ValueError("Debe definir 'nodes' (multi-node) o 'runtime' (simple)")
        return self

    def get_effective_nodes(self) -> List[UpstreamNodeConfig]:
        """Retorna lista de nodos efectivos (convierte runtime simple a nodo)."""
        if self.nodes:
            return self.nodes
        if self.runtime:
            # Crear nodo único desde runtime/tech
            return [
                UpstreamNodeConfig(
                    name=f"{self.name}_default",
                    weight=100,
                    runtime=self.runtime,
                    tech=self.tech,
                )
            ]
        return []

    def is_multi_node(self) -> bool:
        """True si tiene múltiples nodos."""
        return self.nodes is not None and len(self.nodes) > 1


class UpstreamDefDocument(BaseModel):
    """Documento YAML de un upstream (raíz upstream: {...})."""
    upstream: UpstreamDefConfig


# --- Helpers para migración ---

def migrate_dict_routes_to_list(routes_dict: Dict[str, Any]) -> List[RouteConfig]:
    """
    Convierte routes dict (formato antiguo) a lista (formato nuevo).
    Genera name desde el path: /api/identity/ → api_identity
    """
    result = []
    for path_key, route_data in routes_dict.items():
        if not isinstance(route_data, dict):
            continue
        
        # Generar name desde path
        name = path_key.strip("/").replace("/", "_").replace("-", "_")
        if not name:
            name = "root"
        
        # Obtener uri o crear default
        uri_data = route_data.get("uri")
        if uri_data:
            uri = UriTransformConfig(**uri_data) if isinstance(uri_data, dict) else uri_data
        else:
            # Inferir uri
            strategy = "passthrough" if path_key == "/" else "strip"
            uri = UriTransformConfig(
                public=path_key,
                upstream="/",
                strategy=strategy,
            )
        
        route = RouteConfig(
            name=name,
            type=route_data.get("type", "proxy"),
            upstream_ref=route_data.get("upstream_ref", ""),
            uri=uri,
        )
        result.append(route)
    
    return result
