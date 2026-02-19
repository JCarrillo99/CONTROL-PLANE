"""
Modelo de dominio para el sistema de routing de LSX Tool.

SEPARACIÓN CONCEPTUAL (clave para reproducibilidad y validación):

  ┌─────────────────────────────────────────────────────────────────────────┐
  │ ROUTING STRATEGY (estrategia = intención / patrón de despliegue)         │
  │ "¿Por qué enrutamos así?"                                                │
  │ simple, canary, failover, blue_green, mirror                             │
  └─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │  determina
                                    ▼
  ┌─────────────────────────────────────────────────────────────────────────┐
  │ ROUTING ALGORITHM (algoritmo = matemática de reparto)                    │
  │ "¿Cómo repartimos el tráfico entre nodos?"                               │
  │ round_robin, least_conn, ip_hash, hash_uri, weighted                     │
  └─────────────────────────────────────────────────────────────────────────┘

weighted es un ALGORITHM, no una strategy. Ejemplo: simple + weighted, canary + weighted.
"""

from typing import Literal, FrozenSet, Tuple, List, Optional
from enum import Enum


# --- Tipos base (usar Literal para serialización YAML/JSON) ---

Role = Literal["frontend", "api"]
AccessType = Literal["internal", "external", "mixed"]
UriStrategy = Literal["strip", "passthrough"]

# Estrategia = intención de despliegue (por qué)
RoutingStrategy = Literal["simple", "canary", "failover", "blue_green", "mirror"]

# Algoritmo = mecánica de distribución (cómo)
RoutingAlgorithm = Literal["round_robin", "least_conn", "ip_hash", "hash_uri", "weighted"]

# Modo canary (solo si strategy == canary)
CanaryMode = Literal["percentage", "header", "cookie"]


# --- Combinaciones válidas (strategy → algoritmos permitidos) ---

# simple: cualquier algoritmo
SIMPLE_ALGORITHMS: FrozenSet[RoutingAlgorithm] = frozenset({
    "round_robin", "least_conn", "ip_hash", "hash_uri", "weighted"
})

# canary: solo weighted (reparto por porcentaje)
# canary + ip_hash inválido: ip_hash no permite control de % canary
CANARY_ALGORITHMS: FrozenSet[RoutingAlgorithm] = frozenset({"weighted"})

# failover: round_robin o least_conn (distribución simple en primario)
# failover + ip_hash inválido: conflicto con prioridad de failover
FAILOVER_ALGORITHMS: FrozenSet[RoutingAlgorithm] = frozenset({"round_robin", "least_conn"})

# blue_green: sin algoritmo explícito (switch 100% todo-o-nada)
# blue_green + round_robin inválido: round_robin repartiría, blue_green no
BLUE_GREEN_ALGORITHMS: FrozenSet[RoutingAlgorithm] = frozenset()  # vacío = no aplica

# mirror: round_robin (primario recibe round_robin, shadow recibe copia)
# mirror + least_conn inválido: mirror necesita distribución predecible
MIRROR_ALGORITHMS: FrozenSet[RoutingAlgorithm] = frozenset({"round_robin"})


VALID_STRATEGY_ALGORITHMS: dict[str, FrozenSet[RoutingAlgorithm]] = {
    "simple": SIMPLE_ALGORITHMS,
    "canary": CANARY_ALGORITHMS,
    "failover": FAILOVER_ALGORITHMS,
    "blue_green": BLUE_GREEN_ALGORITHMS,
    "mirror": MIRROR_ALGORITHMS,
}

# Strategies que requieren algoritmo explícito (no blue_green)
STRATEGIES_REQUIRING_ALGORITHM: FrozenSet[str] = frozenset({
    "simple", "canary", "failover", "mirror"
})

# Strategies que NO usan algoritmo (blue_green = switch)
STRATEGIES_WITHOUT_ALGORITHM: FrozenSet[str] = frozenset({"blue_green"})


def get_valid_algorithms_for_strategy(strategy: str) -> List[RoutingAlgorithm]:
    """
    Retorna algoritmos válidos para una estrategia.
    Para blue_green retorna lista vacía (no aplica).
    """
    allowed = VALID_STRATEGY_ALGORITHMS.get(strategy, frozenset())
    return sorted(allowed)


def requires_algorithm(strategy: str) -> bool:
    """True si la estrategia requiere seleccionar algoritmo."""
    return strategy in STRATEGIES_REQUIRING_ALGORITHM


def validate_routing_combination(
    strategy: str,
    algorithm: Optional[str] = None,
    canary_mode: Optional[str] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Valida combinación strategy + algorithm + canary_mode.

    Returns:
        (is_valid, error_message)
        - (True, None) si válido
        - (False, "mensaje") si inválido
    """
    # Strategy válida
    if strategy not in VALID_STRATEGY_ALGORITHMS:
        return False, f"RoutingStrategy inválida: {strategy}"

    # blue_green: no algorithm
    if strategy == "blue_green":
        if algorithm:
            return False, "blue_green no usa algoritmo (switch total)"
        return True, None

    # Otras strategies: algorithm requerido
    if not algorithm:
        if requires_algorithm(strategy):
            return False, f"{strategy} requiere algoritmo (round_robin, weighted, etc.)"
        return True, None

    # Algorithm válido para strategy
    allowed = VALID_STRATEGY_ALGORITHMS[strategy]
    if algorithm not in allowed:
        allowed_str = ", ".join(sorted(allowed))
        return False, f"Combinación inválida: {strategy} + {algorithm}. Permitido: {allowed_str or 'ninguno'}"

    # Canary: validar mode si strategy == canary
    if strategy == "canary" and canary_mode:
        valid_modes = {"percentage", "header", "cookie"}
        if canary_mode not in valid_modes:
            return False, f"CanaryMode inválido: {canary_mode}"

    return True, None


def get_default_algorithm_for_strategy(strategy: str) -> Optional[RoutingAlgorithm]:
    """
    Retorna algoritmo por defecto para una estrategia.
    None para blue_green.
    """
    allowed = get_valid_algorithms_for_strategy(strategy)
    if not allowed:
        return None
    # Preferir round_robin para simple/failover/mirror, weighted para canary
    if "round_robin" in allowed:
        return "round_robin"
    return allowed[0]


# --- Descripciones para CLI (selección por número) ---

ROUTING_STRATEGY_OPTIONS: List[Tuple[str, str]] = [
    ("simple", "Routing directo sin experimentos"),
    ("canary", "Despliegue progresivo"),
    ("failover", "Fallback ante caída"),
    ("blue_green", "Switch total entre versiones"),
    ("mirror", "Duplicación de tráfico (shadow)"),
]

ROUTING_ALGORITHM_OPTIONS: List[Tuple[str, str]] = [
    ("round_robin", "Distribución uniforme (default)"),
    ("least_conn", "Menos conexiones activas"),
    ("ip_hash", "Persistencia por IP cliente"),
    ("hash_uri", "Hash por URI"),
    ("weighted", "Reparto por peso/porcentaje"),
]

CANARY_MODE_OPTIONS: List[Tuple[str, str]] = [
    ("percentage", "Porcentaje aleatorio de tráfico"),
    ("header", "Header explícito (ej. X-Canary)"),
    ("cookie", "Cookie persistente"),
]

# Stickiness = persistencia de ruteo canary (reemplaza mode en UX)
CanaryStickiness = Literal["none", "request", "ip", "cookie", "header"]

STICKINESS_OPTIONS: List[Tuple[str, str]] = [
    ("none", "Sin persistencia (cada request decide)"),
    ("request", "Persistente por request_id (default Nginx)"),
    ("ip", "Persistente por IP del cliente"),
    ("cookie", "Persistente por cookie (ideal UX / A-B testing)"),
    ("header", "Forzado por header (QA / testing interno)"),
]

STICKINESS_NEEDS_KEY: FrozenSet[str] = frozenset({"cookie", "header"})
