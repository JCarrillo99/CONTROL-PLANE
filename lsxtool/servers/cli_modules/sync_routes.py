"""
Mapa declarativo de rutas de sincronización por servicio.
Todas las rutas están relativas a BASE_DIR (lsxtool/servers).
No se hardcodean rutas en el comando sync; se reutiliza esta estructura.
"""

from pathlib import Path
from typing import TypedDict, Literal

# Tipos para una ruta de sincronización
class SyncRoute(TypedDict, total=False):
    src: str           # Ruta relativa a BASE_DIR (archivo o directorio)
    dest: str          # Ruta absoluta destino en el sistema
    label: str         # Etiqueta corta para mostrar (ej: "nginx/conf.d")
    type: Literal["file", "dir"]
    glob: str          # Patrón para archivos en directorios (ej: "*.conf"). Si no se indica, se copian todos
    chown: str         # Usuario:grupo para chown (ej: "traefik:traefik", "root:root")


# Mapa: servicio -> lista de rutas (src → dest)
# Añadir aquí cualquier nueva carpeta o ruta que deba sincronizarse.
SYNC_ROUTES: dict[str, list[SyncRoute]] = {
    "traefik": [
        {
            "src": "traefik/config/traefik-dev.yml",
            "dest": "/etc/traefik/traefik.yml",
            "label": "traefik/config (traefik-dev.yml)",
            "type": "file",
            "chown": "traefik:traefik",
        },
        {
            "src": "traefik/config/dynamic",
            "dest": "/etc/traefik/dynamic",
            "label": "traefik/dynamic",
            "type": "dir",
            "glob": "*.yml",
            "chown": "traefik:traefik",
        },
    ],
    "nginx": [
        {
            "src": "nginx/configuration/etc/nginx/conf.d",
            "dest": "/etc/nginx/conf.d",
            "label": "nginx/conf.d",
            "type": "dir",
            "glob": "*.conf",
        },
        {
            "src": "nginx/configuration/etc/nginx/stream.d",
            "dest": "/etc/nginx/stream.d",
            "label": "nginx/stream.d",
            "type": "dir",
        },
        {
            "src": "nginx/configuration/etc/nginx/snippets",
            "dest": "/etc/nginx/snippets",
            "label": "nginx/snippets",
            "type": "dir",
            "glob": "*.conf",
        },
    ],
    "apache": [
        {
            "src": "apache/configuration/etc/apache2/sites-available",
            "dest": "/etc/apache2/sites-available",
            "label": "apache/sites-available",
            "type": "dir",
            "glob": "*.conf",
        },
    ],
}


def get_routes(service: str) -> list[SyncRoute]:
    """Devuelve la lista de rutas para un servicio."""
    return SYNC_ROUTES.get(service, [])
