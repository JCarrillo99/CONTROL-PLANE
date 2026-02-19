"""
Contratos y base para providers de infraestructura.

Los providers (nginx, apache, traefik, dns, servers) implementan estos contratos;
el core no depende de ningún provider concreto.
"""

from atlas.core.infra.contracts import ProviderContract, PlanResult

__all__ = ["ProviderContract", "PlanResult"]
