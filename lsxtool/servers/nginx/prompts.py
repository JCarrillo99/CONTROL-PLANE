"""
Menús interactivos numerados para el wizard de bootstrap.
UX profesional: selección por número, descripciones cortas, validación.
Usa routing_domain para combinaciones strategy+algorithm válidas.
"""

from typing import List, Tuple, Optional
from rich.console import Console
from rich.prompt import Prompt

from ..declarative.routing_domain import (
    ROUTING_STRATEGY_OPTIONS,
    ROUTING_ALGORITHM_OPTIONS,
    CANARY_MODE_OPTIONS,
    STICKINESS_OPTIONS,
    STICKINESS_NEEDS_KEY,
    get_valid_algorithms_for_strategy,
    requires_algorithm,
    get_default_algorithm_for_strategy,
    validate_routing_combination,
)


# --- Route Type ---

ROUTE_TYPE_OPTIONS: List[Tuple[str, str]] = [
    ("proxy", "Redirige tráfico a un servicio"),
    ("static", "Contenido estático (futuro)"),
    ("redirect", "Redirección HTTP (futuro)"),
]

# --- URI Strategy (por ruta) ---

URI_STRATEGY_OPTIONS: List[Tuple[str, str]] = [
    ("passthrough", "No modificar URI"),
    ("strip", "Eliminar prefijo del path"),
    ("rewrite", "Reescritura personalizada (futuro)"),
]

# --- Tech Language ---

TECH_LANGUAGES: List[Tuple[str, str]] = [
    ("node", "Node.js services (NestJS, Express)"),
    ("php", "PHP services (FPM, built-in server)"),
    ("python", "Python services (FastAPI, Flask)"),
]


def _format_menu(options: List[Tuple[str, str]], indent: str = "  ") -> str:
    """Genera texto del menú numerado."""
    lines = []
    for i, (value, desc) in enumerate(options, 1):
        lines.append(f"{indent}{i}) {value:<12} - {desc}")
    return "\n".join(lines)


def _parse_number(
    raw: str,
    max_val: int,
    default: int = 1,
) -> int:
    """Parsea número de la entrada, retorna índice 1-based o default."""
    s = (raw or "").strip()
    if not s:
        return default
    try:
        n = int(s)
        if 1 <= n <= max_val:
            return n
    except ValueError:
        pass
    return -1


def prompt_numbered(
    console: Console,
    title: str,
    options: List[Tuple[str, str]],
    default: int = 1,
    prompt_suffix: str = "> ",
) -> str:
    """
    Muestra menú numerado y retorna el valor seleccionado.
    Retorna el valor interno (ej: 'simple', 'node'), no el número.
    """
    console.print(f"\n[bold cyan]{title}[/bold cyan]")
    console.print(_format_menu(options))

    max_val = len(options)

    while True:
        raw = Prompt.ask(prompt_suffix, default=str(default))
        idx = _parse_number(raw, max_val, default)
        if idx >= 1:
            return options[idx - 1][0]

        console.print(f"[red]Opción inválida. Elige un número entre 1 y {max_val}.[/red]")


def prompt_routing_strategy(console: Console) -> str:
    """
    Menú: Seleccione routing strategy (intención).
    Retorna: simple | canary | failover | blue_green | mirror
    """
    return prompt_numbered(
        console,
        "Seleccione routing strategy (intención de despliegue):",
        ROUTING_STRATEGY_OPTIONS,
        default=1,
    )


def prompt_routing_algorithm(
    console: Console,
    strategy: str,
) -> Optional[str]:
    """
    Menú: Seleccione algoritmo (solo algoritmos válidos para la strategy).
    Retorna algoritmo o None si strategy no requiere (blue_green).
    """
    valid = get_valid_algorithms_for_strategy(strategy)
    if not valid:
        return None

    options = [(v, d) for v, d in ROUTING_ALGORITHM_OPTIONS if v in valid]
    if not options:
        return None

    default_val = get_default_algorithm_for_strategy(strategy)
    default_idx = next((i for i, (v, _) in enumerate(options, 1) if v == default_val), 1)

    return prompt_numbered(
        console,
        "Seleccione algoritmo de balanceo (mecánica de reparto):",
        options,
        default=default_idx,
    )


def prompt_canary_mode(console: Console) -> str:
    """
    Menú: Seleccione modo canary (legacy).
    Retorna: percentage | header | cookie
    """
    return prompt_numbered(
        console,
        "Seleccione modo canary:",
        CANARY_MODE_OPTIONS,
        default=1,
    )


def prompt_stickiness(console: Console) -> str:
    """
    Menú: Stickiness (persistencia de ruteo canary).
    Retorna: none | request | ip | cookie | header
    """
    return prompt_numbered(
        console,
        "Seleccione stickiness (persistencia de ruteo):",
        STICKINESS_OPTIONS,
        default=1,
    )


def prompt_sticky_key(console: Console, ref: str, stickiness: str) -> str:
    """
    Pide key para cookie/header. Default: lsx_<slug>_canary.
    """
    slug = ref.split("__")[-1] if "__" in ref else ref
    default = f"lsx_{slug}_canary"
    return (
        Prompt.ask(f"  Stickiness key ({default})", default=default).strip()
        or default
    )


def prompt_route_type(console: Console) -> str:
    """Menú: Tipo de ruta. Retorna proxy | static | redirect."""
    return prompt_numbered(
        console,
        "Tipo de ruta:",
        ROUTE_TYPE_OPTIONS,
        default=1,
    )


def prompt_uri_strategy(console: Console, path: str = "/") -> str:
    """Menú: Estrategia URI por ruta. Default según path: / → passthrough, /api/... → strip."""
    default_idx = 1 if path == "/" else 2  # passthrough=1, strip=2
    return prompt_numbered(
        console,
        "Estrategia de URI:",
        URI_STRATEGY_OPTIONS[:2],  # solo passthrough y strip por ahora
        default=default_idx,
    )


def prompt_upstream_source(console: Console) -> str:
    """¿Usar upstream existente o crear nuevo? Retorna 'existing' | 'new'."""
    options = [
        ("existing", "Usar upstream existente"),
        ("new", "Crear nuevo upstream"),
    ]
    return prompt_numbered(console, "¿Esta ruta usa un upstream existente o uno nuevo?", options, default=2)


def prompt_tech_language(console: Console) -> str:
    """
    Menú: Seleccione lenguaje del servicio.
    Retorna: node | php | python
    """
    return prompt_numbered(
        console,
        "Seleccione lenguaje del servicio:",
        TECH_LANGUAGES,
        default=1,
    )


def needs_algorithm(strategy: str) -> bool:
    """True si la strategy requiere seleccionar algorithm."""
    return requires_algorithm(strategy)


def get_strategy_by_value(value: str) -> Optional[str]:
    """Valida y retorna strategy; None si inválida."""
    for v, _ in ROUTING_STRATEGY_OPTIONS:
        if v == value:
            return v
    return None


def get_algorithm_by_value(value: str) -> Optional[str]:
    """Valida y retorna algorithm; None si inválido."""
    for v, _ in ROUTING_ALGORITHM_OPTIONS:
        if v == value:
            return v
    return None


def get_language_by_value(value: str) -> Optional[str]:
    """Valida y retorna language; None si inválido."""
    for v, _ in TECH_LANGUAGES:
        if v == value:
            return v
    return None


def validate_strategy_algorithm_combo(strategy: str, algorithm: Optional[str]) -> Tuple[bool, Optional[str]]:
    """Valida combinación strategy+algorithm. Retorna (ok, error_msg)."""
    return validate_routing_combination(strategy, algorithm, None)
