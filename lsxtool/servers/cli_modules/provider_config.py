"""
Carga de configuración de provider.
- Modo desarrollo (LSXTOOL_DEV=1): lee/escribe en .lsxtool del proyecto.
- Modo producción: lee/escribe en ~/.lsxtool del usuario que ejecutó (con sudo, se usa SUDO_USER).
"""

import os
import yaml
from pathlib import Path
from typing import Optional

# Raíz del repo (donde está .lsxtool y .env)
def _repo_root() -> Optional[Path]:
    """Sube desde el directorio de este archivo hasta encontrar un directorio que contenga .lsxtool."""
    try:
        p = Path(__file__).resolve().parent
        for _ in range(10):  # límite de profundidad
            if (p / ".lsxtool").exists():
                return p
            parent = p.parent
            if parent == p:
                break
            p = parent
    except Exception:
        pass
    return None


# Cargar .env desde la raíz del repo primero (así funciona con sudo aunque cwd sea /root)
def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
        repo = _repo_root()
        if repo is not None:
            env_file = repo / ".env"
            if env_file.exists():
                load_dotenv(env_file)
                return
        if (Path.cwd() / ".env").exists():
            load_dotenv(Path.cwd() / ".env")
    except ImportError:
        pass

_load_dotenv()


def _find_project_config_dir() -> Optional[Path]:
    """Busca .lsxtool/config en el proyecto (cwd o padres, o junto al paquete lsxtool)."""
    candidates = list(Path.cwd().parents) + [Path.cwd()]
    # Raíz del repo: __file__ = .../lsxtool/servers/cli_modules/provider_config.py → parents[3] = repo root
    try:
        repo_root = Path(__file__).resolve().parents[3]
        config_dir = repo_root / ".lsxtool" / "config"
        if config_dir.is_dir():
            return config_dir
    except IndexError:
        pass
    for d in candidates:
        config_dir = d / ".lsxtool" / "config"
        if config_dir.is_dir():
            return config_dir
    return None


def get_config_dir() -> Path:
    """
    Directorio de configuración de providers.
    - LSXTOOL_CONFIG_DIR (env): usa esta ruta (útil en .env o prod).
    - LSXTOOL_DEV=1|true: usa .lsxtool/config del proyecto (desarrollo).
    - Si existe .lsxtool/config en el repo (donde está el código): se usa (auto desarrollo).
    - Por defecto: ~/.lsxtool/config (usuario que ejecuta).
    """
    explicit = os.environ.get("LSXTOOL_CONFIG_DIR", "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()

    if os.environ.get("LSXTOOL_DEV", "").strip().lower() in ("1", "true", "yes"):
        project_config = _find_project_config_dir()
        if project_config is not None:
            return project_config

    # Auto desarrollo: si el código está dentro del repo y existe .lsxtool, usar proyecto/.lsxtool/config
    # (se crea config/ al guardar si no existe)
    repo = _repo_root()
    if repo is not None and (repo / ".lsxtool").exists():
        return repo / ".lsxtool" / "config"

    # Producción: usuario que ejecutó (con sudo, no usar /root)
    return get_effective_home() / ".lsxtool" / "config"


def list_configured_provider_ids() -> list[str]:
    """
    IDs de providers que tienen archivo de config en .lsxtool/config/*.yaml.
    Usado por 'servers status' para preguntar de qué provider ver cuando no hay servidores.
    """
    config_dir = get_config_dir()
    if not config_dir.exists():
        return []
    return sorted(
        p.stem for p in config_dir.glob("*.yaml")
        if p.stem and not p.name.startswith(".")
    )


def get_effective_home() -> Path:
    """
    Home del usuario que realmente ejecutó el comando.
    Con sudo: devuelve el home de SUDO_USER (ej. /home/debian-trixie), no /root.
    """
    if os.geteuid() == 0:
        sudo_user = os.environ.get("SUDO_USER", "").strip()
        if sudo_user:
            try:
                import pwd
                return Path(pwd.getpwnam(sudo_user).pw_dir)
            except (ImportError, KeyError):
                pass
            # Fallback Linux
            for prefix in ("/home", "/Users"):
                p = Path(prefix) / sudo_user
                if p.exists():
                    return p
    return Path.home()


def get_effective_user_and_group() -> Optional[tuple[str, str]]:
    """
    (user, group) del usuario que ejecutó el comando, para chown del workspace.
    Con sudo: devuelve SUDO_USER y su grupo primario; si no, None (no hace falta chown).
    """
    if os.geteuid() != 0:
        return None
    sudo_user = os.environ.get("SUDO_USER", "").strip()
    if not sudo_user:
        return None
    try:
        import pwd
        pw = pwd.getpwnam(sudo_user)
        # pw_gid es el grupo primario; grp.getgrgid(pw.pw_gid).gr_name para el nombre
        try:
            import grp
            group_name = grp.getgrgid(pw.pw_gid).gr_name
        except (ImportError, KeyError):
            group_name = sudo_user
        return (sudo_user, group_name)
    except (ImportError, KeyError):
        return (sudo_user, sudo_user)


def get_lsxtool_base_dir() -> Path:
    """
    Directorio base .lsxtool para leer config y escribir salidas (providers, etc.).
    - LSXTOOL_CONFIG_DIR: usa esta ruta.
    - Dev (LSXTOOL_DEV): proyecto/.lsxtool vía _repo_root().
    - Repo con .lsxtool/config: proyecto/.lsxtool (por __file__).
    - Cwd o padres con .lsxtool/catalog: para sudo desde el proyecto.
    - Prod: effective_home/.lsxtool.
    """
    explicit = os.environ.get("LSXTOOL_CONFIG_DIR", "").strip()
    if explicit:
        base = Path(explicit).expanduser().resolve()
        if base.name == "config":
            base = base.parent
        return base

    if os.environ.get("LSXTOOL_DEV", "").strip().lower() in ("1", "true", "yes"):
        repo = _repo_root()
        if repo is not None:
            return repo / ".lsxtool"

    repo = _repo_root()
    if repo is not None and (repo / ".lsxtool" / "config").is_dir():
        return repo / ".lsxtool"

    # Fallback: cwd o padres (útil con sudo cuando se ejecuta desde el proyecto)
    for d in [Path.cwd(), *Path.cwd().parents]:
        lsx = d / ".lsxtool"
        if (lsx / "catalog").is_dir() or (lsx / "config").is_dir():
            return lsx

    return get_effective_home() / ".lsxtool"


def get_provider_config_path(provider_id: str) -> Path:
    """Ruta del archivo YAML de configuración del provider."""
    return get_config_dir() / f"{provider_id}.yaml"


def load_provider_config(provider_id: str) -> Optional[dict]:
    """
    Carga la configuración del provider desde ~/.lsxtool/config/{provider_id}.yaml.
    Devuelve None si el archivo no existe o no es válido.
    """
    path = get_provider_config_path(provider_id)
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return None


def get_servers_web_capability(provider_config: dict) -> Optional[dict]:
    """
    Obtiene la capacidad servers_web del provider.
    Devuelve None si no está definida.
    Estructura esperada:
      capabilities:
        servers_web:
          services: [nginx, apache, ...]
          targets: [host, docker]
          environments: [dev, qa, prod]
    """
    capabilities = provider_config.get("capabilities") or {}
    return capabilities.get("servers_web")


class MissingCapabilityError(Exception):
    """Se lanza cuando el provider no tiene definida una capacidad requerida."""
    def __init__(self, provider_id: str, capability_key: str, config_path: Path):
        self.provider_id = provider_id
        self.capability_key = capability_key
        self.config_path = config_path
        super().__init__(
            f"El provider '{provider_id}' no tiene definida la capacidad: {capability_key}"
        )


# Etiquetas para mostrar en `providers configure` (solo presentación)
CAPABILITY_LABELS = {
    "servers_web": "Servidor web (Nginx, Apache, Traefik, etc.)",
    "servers_database": "Servidor base de datos (Postgres, MySQL, Redis, etc.)",
    "servers_mail": "Servidor de correo",
    "servers_cache": "Servidor de caché",
    "servers_queue": "Servidor de colas",
}


def get_capability_label(key: str) -> str:
    """Devuelve la etiqueta legible de una capacidad."""
    return CAPABILITY_LABELS.get(key, key.replace("_", " ").title())
