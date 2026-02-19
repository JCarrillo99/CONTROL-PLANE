"""
Carga y guardado del catálogo de upstreams.
Soporta convención: .lsxtool/providers/<provider>/servers/<server>/<env>/<ref>.yaml
y legacy: .lsxtool/upstreams/<ref>.yaml
"""

import yaml
from pathlib import Path
from typing import Optional, Dict, List
from rich.console import Console

from .upstream_catalog import UpstreamCatalogDef
from . import get_declarative_root, chown_to_project_owner
from .upstream_convention import convention_path, convention_dir, upstreams_dir


def _name_to_filename(name: str) -> str:
    """Nombre lógico (api_identity_dev) -> nombre de archivo (api-identity-dev.yaml)."""
    return name.replace("_", "-") + ".yaml"


def _filename_to_name(path: Path) -> str:
    """Archivo (api-identity-dev.yaml) -> nombre lógico (api_identity_dev)."""
    return path.stem.replace("-", "_")


def get_upstreams_dir(base_dir: Path) -> Path:
    """Ruta a .lsxtool/upstreams/."""
    root = get_declarative_root(base_dir)
    d = root / "upstreams"
    d.mkdir(parents=True, exist_ok=True)
    chown_to_project_owner(d, base_dir, recursive=True)
    return d


class UpstreamCatalogLoader:
    """Carga y guarda upstreams del catálogo."""

    def __init__(self, base_dir: Path, console: Optional[Console] = None):
        self.base_dir = base_dir
        self.console = console or Console()
        self.upstreams_dir = get_upstreams_dir(base_dir)
        self._cache: Dict[str, UpstreamCatalogDef] = {}

    def list_names(self, provider_id: Optional[str] = None, environment: Optional[str] = None, server: Optional[str] = None) -> List[str]:
        """Lista los nombres lógicos de upstreams (canónico providers/.../upstreams/ y legacy upstreams/)."""
        names = []
        root = get_declarative_root(self.base_dir)
        # Canónico: providers/<id>/environments/<env>/servers/<server>/upstreams/*.yaml
        providers_dir = root / "providers"
        if providers_dir.exists():
            for prov_dir in providers_dir.iterdir():
                if not prov_dir.is_dir() or (provider_id and prov_dir.name != provider_id):
                    continue
                envs = prov_dir / "environments"
                if not envs.exists():
                    continue
                for env_dir in envs.iterdir():
                    if not env_dir.is_dir() or (environment and env_dir.name != environment):
                        continue
                    servers_dir = env_dir / "servers"
                    if not servers_dir.exists():
                        continue
                    for srv_dir in servers_dir.iterdir():
                        if not srv_dir.is_dir() or (server and srv_dir.name != server):
                            continue
                        up_dir = srv_dir / "upstreams"
                        if not up_dir.exists():
                            continue
                        for p in up_dir.glob("*.yaml"):
                            try:
                                with open(p, "r") as f:
                                    data = yaml.safe_load(f) or {}
                                names.append(data.get("name", p.stem))
                            except Exception:
                                names.append(p.stem)
        # Legacy: .lsxtool/upstreams/
        for p in self.upstreams_dir.glob("*.yaml"):
            try:
                with open(p, "r") as f:
                    data = yaml.safe_load(f) or {}
                names.append(data.get("name", _filename_to_name(p)))
            except Exception:
                names.append(_filename_to_name(p))
        return sorted(set(names))

    def load_from_path(self, path: Path) -> Optional[UpstreamCatalogDef]:
        """Carga un upstream desde una ruta YAML."""
        if not path.exists():
            return None
        cache_key = str(path)
        if cache_key in self._cache:
            return self._cache[cache_key]
        try:
            with open(path, "r") as f:
                data = yaml.safe_load(f) or {}
            defn = UpstreamCatalogDef(**data)
            self._cache[cache_key] = defn
            self._cache[defn.name] = defn
            return defn
        except Exception as e:
            if self.console:
                self.console.print(f"[red]❌ Error al cargar {path.name}: {e}[/red]")
            return None

    def load_by_convention(
        self, provider: str, server: str, environment: str, ref_name: str
    ) -> Optional[UpstreamCatalogDef]:
        """Carga un upstream por convención: providers/<provider>/servers/<server>/<env>/<ref>.yaml"""
        path = convention_path(self.base_dir, provider, server, environment, ref_name)
        return self.load_from_path(path)

    def load(self, ref_name: str, provider: Optional[str] = None, server: Optional[str] = None, environment: Optional[str] = None) -> Optional[UpstreamCatalogDef]:
        """
        Carga un upstream por nombre lógico.
        Si se pasan provider, server, environment, intenta primero por convención.
        Luego legacy: .lsxtool/upstreams/ (api_identity_dev -> api-identity-dev.yaml).
        """
        if ref_name in self._cache:
            return self._cache[ref_name]

        # 1) Convención (si tenemos contexto)
        if provider and server and environment:
            defn = self.load_by_convention(provider, server, environment, ref_name)
            if defn:
                return defn

        # 2) Legacy: flat upstreams/
        fname = _name_to_filename(ref_name)
        path = self.upstreams_dir / fname
        if path.exists():
            try:
                with open(path, "r") as f:
                    data = yaml.safe_load(f) or {}
                defn = UpstreamCatalogDef(**data)
                self._cache[ref_name] = defn
                return defn
            except Exception as e:
                if self.console:
                    self.console.print(f"[red]❌ Error al cargar upstream {ref_name}: {e}[/red]")
                return None

        for p in self.upstreams_dir.glob("*.yaml"):
            try:
                with open(p, "r") as f:
                    data = yaml.safe_load(f) or {}
                if data.get("name") == ref_name:
                    defn = UpstreamCatalogDef(**data)
                    self._cache[ref_name] = defn
                    return defn
            except Exception:
                continue
        return None

    def save(self, defn: UpstreamCatalogDef, to_convention: Optional[tuple] = None) -> bool:
        """
        Guarda un upstream en el catálogo.
        to_convention: (provider, server, environment) para guardar por convención; si None, legacy .lsxtool/upstreams/
        """
        if to_convention:
            provider, server, env = to_convention
            path = convention_path(self.base_dir, provider, server, env, defn.name)
        else:
            fname = _name_to_filename(defn.name)
            path = self.upstreams_dir / fname
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            chown_to_project_owner(path.parent, self.base_dir)
            with open(path, "w") as f:
                yaml.dump(
                    defn.model_dump(exclude_none=True),
                    f,
                    default_flow_style=False,
                    sort_keys=False,
                    allow_unicode=True,
                )
            chown_to_project_owner(path, self.base_dir)
            self._cache[defn.name] = defn
            return True
        except Exception as e:
            if self.console:
                self.console.print(f"[red]❌ Error al guardar upstream {defn.name}: {e}[/red]")
            return False

    def exists(self, ref_name: str, provider: Optional[str] = None, server: Optional[str] = None, environment: Optional[str] = None) -> bool:
        """Indica si existe un upstream con ese nombre (por convención o legacy)."""
        if provider and server and environment:
            path = convention_path(self.base_dir, provider, server, environment, ref_name)
            if path.exists():
                return True
        return self.load(ref_name, provider, server, environment) is not None
