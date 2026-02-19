"""
Catálogo declarativo: providers reales (no namespace interno).
Provider = identificador real (lunarsystemx), viene del catálogo.
"""

import yaml
from pathlib import Path
from typing import Optional, List, Dict, Any

from . import get_declarative_root, chown_to_project_owner


def get_catalog_dir(base_dir: Path) -> Path:
    """Ruta a .lsxtool/catalog/."""
    root = get_declarative_root(base_dir)
    d = root / "catalog"
    d.mkdir(parents=True, exist_ok=True)
    chown_to_project_owner(d, base_dir)
    return d


def load_providers_catalog(base_dir: Path) -> List[Dict[str, Any]]:
    """
    Carga .lsxtool/catalog/providers.yaml.
    Formato esperado:
      providers:
        - id: lunarsystemx
          name: Lunar System X
          domain_suffix: lunarsystemx.com   # *.lunarsystemx.com → este provider
          internal_namespace: LSX           # opcional, marca interna
    """
    catalog_dir = get_catalog_dir(base_dir)
    path = catalog_dir / "providers.yaml"
    if not path.exists():
        return []
    try:
        with open(path, "r") as f:
            data = yaml.safe_load(f) or {}
        return data.get("providers", data.get("provider_list", []))
    except Exception:
        return []


def resolve_provider_from_domain(base_dir: Path, domain: str) -> Optional[str]:
    """
    Resuelve el provider real (id) a partir del dominio usando el catálogo.
    Ej: dev-identity.lunarsystemx.com → lunarsystemx (si en catálogo hay domain_suffix: lunarsystemx.com).
    """
    providers = load_providers_catalog(base_dir)
    if not providers:
        # Fallback: extraer del dominio (últimas dos partes antes del TLD)
        # dev-identity.lunarsystemx.com → lunarsystemx
        parts = domain.strip().lower().split(".")
        if len(parts) >= 2:
            return parts[-2]
        return None
    domain_lower = domain.strip().lower()
    for p in providers:
        if isinstance(p, dict):
            suffix = (p.get("domain_suffix") or p.get("domain") or "").strip().lower()
            if suffix and (domain_lower == suffix or domain_lower.endswith("." + suffix)):
                return (p.get("id") or p.get("name") or "").strip()
    return None


def resolve_provider_id(base_dir: Path, domain: Optional[str] = None, meta_provider: Optional[str] = None) -> Optional[str]:
    """
    Obtiene el provider real (id) para rutas.
    Si meta_provider es "LSX" y en catálogo hay internal_namespace: LSX → id lunarsystemx.
    Si domain se pasa, primero se intenta por dominio.
    """
    if domain:
        pid = resolve_provider_from_domain(base_dir, domain)
        if pid:
            return pid
    providers = load_providers_catalog(base_dir)
    if not meta_provider:
        return None
    meta_clean = (meta_provider or "").strip().upper()
    for p in providers:
        if isinstance(p, dict):
            ns = (p.get("internal_namespace") or p.get("namespace") or "").strip().upper()
            if ns and ns == meta_clean:
                return (p.get("id") or p.get("name") or "").strip()
            if (p.get("id") or p.get("name") or "").strip().upper() == meta_clean:
                return (p.get("id") or p.get("name") or "").strip()
    return meta_provider.strip().lower()
