"""
Catálogo de capacidades por tech.language.
Reglas: PHP → provider opcional (system); Node → provider obligatorio; corrección provider/manager.
"""

from typing import Dict, List, Any

TECH_CAPABILITIES: Dict[str, Dict[str, Any]] = {
    "node": {
        "providers": ["volta", "nvm", "asdf", "system"],
        "managers": ["npm", "yarn", "pnpm", "bun"],
        "provider_required": True,
        "default_version": "20",
        "default_provider": "volta",
        "default_manager": "yarn",
    },
    "php": {
        "providers": ["system"],
        "managers": ["composer"],
        "provider_required": False,
        "default_version": "7.2",
        "default_provider": "system",
        "default_manager": "composer",
    },
    "python": {
        "providers": ["pyenv", "system"],
        "managers": ["pip", "poetry", "pipenv"],
        "provider_required": False,
        "default_version": "3.11",
        "default_provider": "system",
        "default_manager": "pip",
    },
}

# Todos los managers (para detectar "composer" escrito en provider)
ALL_MANAGERS = ["npm", "yarn", "pnpm", "bun", "composer", "pip", "poetry", "pipenv"]


def is_manager(value: str) -> bool:
    return (value or "").strip().lower() in [m.lower() for m in ALL_MANAGERS]


def get_capabilities(lang: str) -> Dict[str, Any]:
    lang = (lang or "node").strip().lower()
    return TECH_CAPABILITIES.get(lang, TECH_CAPABILITIES["node"])


def resolve_provider_input(lang: str, raw: str, _console=None) -> str:
    """
    Si el usuario escribe un tech_manager (ej. composer) en tech.provider, retorna system.
    El mensaje de corrección se muestra en el bootstrap al usar manager detectado.
    """
    raw = (raw or "").strip().lower()
    cap = get_capabilities(lang)
    if not raw:
        return cap.get("default_provider", "system")
    if is_manager(raw):
        return "system"
    valid = [p.lower() for p in cap.get("providers", [])]
    return raw if raw in valid else (cap.get("default_provider") or "system")


def resolve_manager_input(lang: str, raw: str) -> str:
    """Valida manager contra catálogo; si no válido, usa default."""
    raw = (raw or "").strip().lower()
    cap = get_capabilities(lang)
    valid = [m.lower() for m in cap.get("managers", [])]
    if raw in valid:
        return raw
    return cap.get("default_manager", "yarn")
