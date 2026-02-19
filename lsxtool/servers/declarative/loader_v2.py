"""
Loader v2: providers/.../servers/nginx/<env>/sites/<domain>.yaml (frontends) y upstreams v2.
Soporta: routes como lista o dict (migración automática), upstreams multi-node.
"""

import yaml
from pathlib import Path
from typing import Optional, Dict, Any, List
from rich.console import Console

from . import get_declarative_root, chown_to_project_owner
from .convention_v2 import site_path, find_site_path_for_domain, upstream_path_v2, upstreams_dir_v2, list_upstream_refs_v2
from .models_v2 import (
    FrontendDomainConfig,
    UpstreamDefConfig,
    RouteConfig,
    UriTransformConfig,
    migrate_dict_routes_to_list,
)


def _normalize_routes(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normaliza routes: si es dict, lo convierte a lista.
    Esto permite retrocompatibilidad con el formato antiguo.
    """
    routes = data.get("routes")
    if routes is None:
        data["routes"] = []
        return data
    
    # Ya es lista → ok
    if isinstance(routes, list):
        return data
    
    # Es dict → convertir a lista
    if isinstance(routes, dict):
        converted = []
        for path_key, route_data in routes.items():
            if not isinstance(route_data, dict):
                continue
            
            # Generar name desde path
            name = path_key.strip("/").replace("/", "_").replace("-", "_")
            if not name:
                name = "root"
            
            # Obtener o crear uri
            uri_data = route_data.get("uri")
            if not uri_data:
                strategy = "passthrough" if path_key == "/" else "strip"
                uri_data = {
                    "public": path_key,
                    "upstream": "/",
                    "strategy": strategy,
                }
            
            converted.append({
                "name": name,
                "type": route_data.get("type", "proxy"),
                "upstream_ref": route_data.get("upstream_ref", ""),
                "uri": uri_data,
            })
        
        data["routes"] = converted
    
    return data


def load_domain(
    base_dir: Path,
    domain: str,
    provider_id: Optional[str] = None,
    env: Optional[str] = None,
    console: Optional[Console] = None,
) -> Optional[FrontendDomainConfig]:
    """Carga frontend domain desde providers/.../sites/<domain>.yaml. Si provider/env no se pasan, busca en todos."""
    if provider_id and env:
        path = site_path(base_dir, provider_id, env, domain)
    else:
        found, provider_id, env = find_site_path_for_domain(base_dir, domain)
        path = found
    if not path or not path.exists():
        return None
    try:
        with open(path, "r") as f:
            data = yaml.safe_load(f) or {}
        
        # Normalizar routes (dict → lista si necesario)
        data = _normalize_routes(data)
        
        return FrontendDomainConfig(**data)
    except Exception as e:
        if console:
            console.print(f"[red]❌ Error al cargar {path.name}: {e}[/red]")
        return None


def _routes_to_yaml_format(routes: List[RouteConfig]) -> List[Dict[str, Any]]:
    """Convierte lista de RouteConfig a formato YAML amigable."""
    result = []
    for route in routes:
        if isinstance(route, dict):
            result.append(route)
        else:
            route_dict = route.model_dump(exclude_none=True)
            result.append(route_dict)
    return result


def save_domain(
    base_dir: Path,
    config: FrontendDomainConfig,
    provider_id: str,
    env: str,
    console: Optional[Console] = None,
) -> bool:
    """Guarda frontend domain en providers/.../servers/nginx/<env>/sites/<domain>.yaml."""
    path = site_path(base_dir, provider_id, env, config.domain)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        chown_to_project_owner(path.parent, base_dir)
        
        # model_dump con routes como lista
        dump = config.model_dump(by_alias=True, exclude_none=True)
        
        with open(path, "w") as f:
            yaml.dump(dump, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
        chown_to_project_owner(path, base_dir)
        return True
    except Exception as e:
        if console:
            console.print(f"[red]❌ Error al guardar {path.name}: {e}[/red]")
        return False


def load_upstream_v2(
    base_dir: Path,
    ref: str,
    provider_id: str,
    env: str,
    console: Optional[Console] = None,
) -> Optional[UpstreamDefConfig]:
    """
    Carga upstream v2 desde providers/.../upstreams/<ref>.yaml.
    Soporta:
    - Formato nuevo: nodes[] para multi-node
    - Formato antiguo: runtime/tech a nivel raíz (retrocompat)
    """
    path = upstream_path_v2(base_dir, provider_id, env, ref)
    if not path.exists():
        return None
    try:
        with open(path, "r") as f:
            data = yaml.safe_load(f) or {}
        if "upstream" not in data:
            return None
        return UpstreamDefConfig(**data["upstream"])
    except Exception as e:
        if console:
            console.print(f"[red]❌ Error al cargar upstream {ref}: {e}[/red]")
        return None


def save_upstream_v2(
    base_dir: Path,
    provider_id: str,
    env: str,
    config: UpstreamDefConfig,
    console: Optional[Console] = None,
) -> bool:
    """Guarda upstream v2 en providers/.../upstreams/<name>.yaml."""
    ref = (config.name or "").strip()
    if not ref:
        return False
    path = upstream_path_v2(base_dir, provider_id, env, ref)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        chown_to_project_owner(path.parent, base_dir)
        doc = {"upstream": config.model_dump(exclude_none=True)}
        with open(path, "w") as f:
            yaml.dump(doc, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
        chown_to_project_owner(path, base_dir)
        return True
    except Exception as e:
        if console:
            console.print(f"[red]❌ Error al guardar upstream {ref}: {e}[/red]")
        return False


def list_upstream_refs(base_dir: Path, provider_id: str, env: str) -> list:
    """Lista refs de upstreams v2."""
    return list_upstream_refs_v2(base_dir, provider_id, env)
