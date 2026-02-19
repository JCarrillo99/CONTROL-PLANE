"""
Convención canónica de upstreams y sites.
Provider = real (lunarsystemx), viene del catálogo. No usar LSX como provider en rutas.

Estructura:
  .lsxtool/providers/<provider>/environments/<env>/servers/<server>/upstreams/<ref>.yaml
  .lsxtool/providers/<provider>/environments/<env>/servers/<server>/sites/<domain>.yaml
"""

from pathlib import Path
from typing import Optional, List, Tuple

from . import get_declarative_root, chown_to_project_owner
from .catalog import resolve_provider_id


def expected_upstream_ref(service_type: str, slug: str) -> str:
    """Nombre lógico esperado: service_type__slug (doble guión bajo)."""
    st = (service_type or "api").strip().lower()
    sl = (slug or "").strip().lower().replace("-", "_")
    return f"{st}__{sl}"


def _server_env_dir(base_dir: Path, provider_id: str, environment: str, server: str) -> Path:
    """Directorio providers/<provider>/environments/<env>/servers/<server>/."""
    root = get_declarative_root(base_dir)
    provider_clean = (provider_id or "").strip().lower()
    env_clean = (environment or "dev").strip().lower()
    server_clean = (server or "nginx").strip().lower()
    return root / "providers" / provider_clean / "environments" / env_clean / "servers" / server_clean


def upstreams_dir(base_dir: Path, provider_id: str, environment: str, server: str) -> Path:
    """Directorio de upstreams: .../servers/<server>/upstreams/."""
    d = _server_env_dir(base_dir, provider_id, environment, server) / "upstreams"
    d.mkdir(parents=True, exist_ok=True)
    chown_to_project_owner(d, base_dir)
    return d


def sites_dir(base_dir: Path, provider_id: str, environment: str, server: str) -> Path:
    """Directorio de sites (domains): .../servers/<server>/sites/."""
    d = _server_env_dir(base_dir, provider_id, environment, server) / "sites"
    d.mkdir(parents=True, exist_ok=True)
    chown_to_project_owner(d, base_dir)
    return d


def convention_dir(base_dir: Path, provider_id: str, server: str, environment: str) -> Path:
    """Directorio de upstreams por convención canónica (alias para compat)."""
    return upstreams_dir(base_dir, provider_id, environment, server)


def convention_path(
    base_dir: Path,
    provider_id: str,
    server: str,
    environment: str,
    upstream_ref: str,
) -> Path:
    """Ruta al YAML del upstream: .../upstreams/<ref>.yaml."""
    d = upstreams_dir(base_dir, provider_id, environment, server)
    ref = (upstream_ref or "").strip()
    return d / f"{ref}.yaml" if ref and not ref.endswith(".yaml") else d / ref


def site_path(
    base_dir: Path,
    provider_id: str,
    environment: str,
    server: str,
    domain: str,
) -> Path:
    """Ruta al YAML del site (domain): .../sites/<domain>.yaml."""
    d = sites_dir(base_dir, provider_id, environment, server)
    return d / f"{domain}.yaml"


def resolve_upstream_by_convention(
    base_dir: Path,
    provider: str,
    server: str,
    environment: str,
    service_type: str,
    slug: str,
    domain: Optional[str] = None,
) -> Tuple[Optional[str], Optional[Path], List[str]]:
    """
    Resuelve el upstream esperado por convención canónica.
    provider: puede ser id real (lunarsystemx) o namespace (LSX); se resuelve a id real vía catálogo.
    Ruta: providers/<provider_id>/environments/<env>/servers/<server>/upstreams/<service_type>__<slug>.yaml
    """
    provider_id = resolve_provider_id(base_dir, domain=domain, meta_provider=provider)
    if not provider_id:
        provider_id = (provider or "").strip().lower()
    ref_expected = expected_upstream_ref(service_type, slug)
    d = upstreams_dir(base_dir, provider_id, environment, server)

    exact_path = d / f"{ref_expected}.yaml"
    if exact_path.exists():
        return (ref_expected, exact_path, [ref_expected])

    compatibles = [p.stem for p in sorted(d.glob("*.yaml"))]
    if len(compatibles) == 0:
        # Fallback legacy: .lsxtool/upstreams/api_identity_dev.yaml
        root = get_declarative_root(base_dir)
        legacy_dir = root / "upstreams"
        legacy_ref = f"{service_type}_{slug}_{environment}".replace("-", "_")
        legacy_path = legacy_dir / f"{legacy_ref.replace('_', '-')}.yaml"
        if legacy_path.exists():
            return (legacy_ref, legacy_path, [legacy_ref])
        return (None, None, [])
    if len(compatibles) == 1:
        return (compatibles[0], d / f"{compatibles[0]}.yaml", compatibles)
    return (None, None, compatibles)
