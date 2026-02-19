"""
Convención v2 (obligatoria): providers/.../servers/nginx/<env>/{sites|upstreams}.

Estructura:
  .lsxtool/providers/<provider>/servers/nginx/<env>/sites/<domain>.yaml
  .lsxtool/providers/<provider>/servers/nginx/<env>/upstreams/<ref>.yaml

❌ Nunca mezclar provider con environment en rutas de forma incorrecta.
❌ No crear YAML huérfanos.
"""

from pathlib import Path
from typing import List, Optional, Tuple

from . import get_declarative_root, chown_to_project_owner


def _env_dir(base_dir: Path, provider_id: str, env: str) -> Path:
    """providers/<provider>/servers/nginx/<env>/"""
    root = get_declarative_root(base_dir)
    return root / "providers" / (provider_id or "").strip().lower() / "servers" / "nginx" / (env or "dev").strip().lower()


def sites_dir(base_dir: Path, provider_id: str, env: str) -> Path:
    """Directorio sites (dominios frontend) para provider/env."""
    d = _env_dir(base_dir, provider_id, env) / "sites"
    d.mkdir(parents=True, exist_ok=True)
    chown_to_project_owner(d, base_dir)
    return d


def site_path(base_dir: Path, provider_id: str, env: str, domain: str) -> Path:
    """Ruta al YAML de dominio frontend: .../sites/<domain>.yaml."""
    return sites_dir(base_dir, provider_id, env) / f"{domain}.yaml"


def upstreams_dir_v2(base_dir: Path, provider_id: str, env: str) -> Path:
    """Directorio upstreams para provider/env."""
    d = _env_dir(base_dir, provider_id, env) / "upstreams"
    d.mkdir(parents=True, exist_ok=True)
    chown_to_project_owner(d, base_dir)
    return d


def upstream_path_v2(base_dir: Path, provider_id: str, env: str, ref: str) -> Path:
    """Ruta al YAML de upstream: .../upstreams/<ref>.yaml. Ref sin .yaml."""
    r = (ref or "").strip()
    if r.endswith(".yaml"):
        r = r[:-5]
    return upstreams_dir_v2(base_dir, provider_id, env) / f"{r}.yaml"


def find_site_path_for_domain(base_dir: Path, domain: str) -> Tuple[Optional[Path], Optional[str], Optional[str]]:
    """Busca providers/.../sites/<domain>.yaml. Retorna (path, provider_id, env) o (None, None, None)."""
    root = get_declarative_root(base_dir) / "providers"
    if not root.exists():
        return (None, None, None)
    for pdir in root.iterdir():
        if not pdir.is_dir():
            continue
        nginx = pdir / "servers" / "nginx"
        if not nginx.exists():
            continue
        for edir in nginx.iterdir():
            if not edir.is_dir():
                continue
            sites = edir / "sites"
            if not sites.exists():
                continue
            path = sites / f"{domain}.yaml"
            if path.exists():
                return (path, pdir.name, edir.name)
    return (None, None, None)


def list_upstream_refs_v2(base_dir: Path, provider_id: str, env: str) -> List[str]:
    """Lista de refs (nombres) de upstreams en upstreams_dir_v2."""
    d = upstreams_dir_v2(base_dir, provider_id, env)
    if not d.exists():
        return []
    return sorted(p.stem for p in d.glob("*.yaml"))


def expected_upstream_ref_v2(service_type: str, slug: str) -> str:
    """Nombre lógico: service_type__slug (doble guión bajo)."""
    st = (service_type or "api").strip().lower()
    sl = (slug or "").strip().lower().replace("-", "_")
    return f"{st}__{sl}"
