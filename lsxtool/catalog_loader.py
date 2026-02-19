"""
Core: carga del catálogo .lsxtool/catalog/ (providers, capabilities, services).
Usado por providers add/configure y servers add.
"""

import yaml
from pathlib import Path
from typing import Optional


def get_catalog_dir(base: Path) -> Path:
    """Directorio catalog dentro de la base .lsxtool."""
    return base / "catalog"


def load_catalog_providers(base: Path) -> list[dict]:
    """Carga catalog/providers.yaml; devuelve lista de providers."""
    path = get_catalog_dir(base) / "providers.yaml"
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            return data.get("providers", [])
    except Exception:
        return []


def load_capability_ids(base: Path) -> list[str]:
    """Lista IDs de capacidades desde catalog/capabilities/*.yaml (nombre del archivo)."""
    cap_dir = get_catalog_dir(base) / "capabilities"
    if not cap_dir.exists():
        return []
    return sorted(
        p.stem for p in cap_dir.glob("*.yaml")
        if p.stem and not p.name.startswith(".")
    )


def load_capability_ids_from_registry(base: Path) -> list[str]:
    """
    Lista IDs de capacidades desde catalog/capabilities.yaml (registro declarado).
    Si el archivo no existe o está vacío, fallback a escanear catalog/capabilities/*.yaml.
    """
    path = get_catalog_dir(base) / "capabilities.yaml"
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            ids = data.get("capabilities")
            if isinstance(ids, list) and ids:
                return [str(x) if isinstance(x, str) else str(x.get("id", x)) for x in ids]
        except Exception:
            pass
    return load_capability_ids(base)


def load_capability_content(base: Path, capability_id: str) -> dict:
    """Carga el contenido de catalog/capabilities/{id}.yaml."""
    path = get_catalog_dir(base) / "capabilities" / f"{capability_id}.yaml"
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def load_server_service_ids(base: Path, server_type: str) -> list[str]:
    """
    Lista IDs de servicios desde catalog/services/servers/{server_type}/*.yaml.
    server_type: web | database
    """
    services_dir = get_catalog_dir(base) / "services" / "servers" / server_type
    if not services_dir.exists():
        return []
    return sorted(
        p.stem for p in services_dir.glob("*.yaml")
        if p.stem and not p.name.startswith(".")
    )


def get_service_config_path(base: Path, server_type: str, service_id: str) -> str:
    """
    Ruta de configuración del servicio en el servidor (ej. /etc/nginx).
    Lee catalog/services/servers/{server_type}/{service_id}.yaml → host.layouts.default.root.
    Si no existe, devuelve un valor por defecto según service_id.
    """
    path = get_catalog_dir(base) / "services" / "servers" / server_type / f"{service_id}.yaml"
    if not path.exists():
        return _default_config_path_for_service(service_id)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception:
        return _default_config_path_for_service(service_id)
    host = data.get("host") or {}
    layouts = host.get("layouts") or {}
    # Preferir layout "default"
    layout = layouts.get("default") or (list(layouts.values())[0] if layouts else {})
    root = layout.get("root") if isinstance(layout, dict) else None
    if root and isinstance(root, str):
        return root.rstrip("/") or root
    return _default_config_path_for_service(service_id)


def _default_config_path_for_service(service_id: str) -> str:
    """Ruta por defecto cuando no está en el catálogo."""
    defaults = {"nginx": "/etc/nginx", "apache": "/etc/apache2", "traefik": "/etc/traefik"}
    return defaults.get(service_id, "/etc/nginx")


def load_server_types_from_capability(base: Path, capability_id: str = "servers") -> list[dict]:
    """
    Carga server_types desde catalog/capabilities/servers.yaml.
    Acepta formato dict (web: { label, services, targets, environments })
    o list ([ { id, default_services, targets }, ... ]).
    Siempre devuelve lista de dicts con id, label (opcional), services/default_services, targets, environments.
    """
    data = load_capability_content(base, capability_id)
    raw = data.get("server_types")
    if raw is None:
        return []
    if isinstance(raw, dict):
        return [
            {
                "id": k,
                "label": v.get("label", k),
                "services": v.get("services", []),
                "targets": v.get("targets", []),
                "environments": v.get("environments", []),
            }
            for k, v in raw.items()
        ]
    return raw


def load_all_provider_capability_keys(base: Path) -> list[str]:
    """
    Todas las claves de capacidad que pueden ir en provider config.
    Lee catalog/capabilities.yaml; para 'servers' expande a servers_web, servers_database.
    Ej.: [security, servers_web, servers_database]
    """
    reg = load_capability_ids_from_registry(base)
    out = []
    for cap_id in reg:
        if cap_id == "servers":
            out.extend(load_configurable_server_capability_ids(base))
        else:
            out.append(cap_id)
    return out


def load_configurable_server_capability_ids(base: Path) -> list[str]:
    """
    IDs de capacidades configurables derivados de servers.yaml server_types.
    Convención: servers_web, servers_database (servers_ + id del server_type).
    """
    data = load_capability_content(base, "servers")
    server_types = data.get("server_types")
    if server_types is None:
        return []
    if isinstance(server_types, dict):
        return [f"servers_{k}" for k in server_types]
    return [f"servers_{st.get('id', '')}" for st in server_types if st.get("id")]


def load_capability_template_from_servers(base: Path, capability_key: str) -> dict:
    """
    Plantilla para provider config (services, targets, environments) desde
    catalog/capabilities/servers.yaml.
    Acepta server_types como dict (web: { services, targets, environments }) o list.
    capability_key: servers_web | servers_database.
    """
    data = load_capability_content(base, "servers")
    server_types = data.get("server_types", [])
    prefix = "servers_"
    if not capability_key.startswith(prefix):
        return {}
    st_id = capability_key[len(prefix) :]

    if isinstance(server_types, dict):
        st = server_types.get(st_id)
        if not st:
            return {}
        services = list(st.get("services") or [])
        targets = list(st.get("targets") or [])
        environments = list(st.get("environments") or [])
        # Opcional: filtrar services por los que existen en catalog/services/servers/{st_id}/
        available = load_server_service_ids(base, st_id)
        if available:
            services = [s for s in services if s in available] or list(available)
        return {"services": services, "targets": targets, "environments": environments}

    # Formato list (legacy)
    st = next((t for t in server_types if t.get("id") == st_id), None)
    if not st:
        return {}
    available = load_server_service_ids(base, st_id)
    default = st.get("default_services") or st.get("services") or []
    services = [s for s in default if s in available] if available else list(default)
    if not services and available:
        services = list(available)
    out = {"services": services, "targets": list(st.get("targets") or [])}
    envs = st.get("environments") or data.get("default_environments")
    if envs:
        out["environments"] = list(envs)
    return out
