"""
Provider Nginx: implementa contrato de infra para Nginx.

La implementación real se delega a lsxtool.servers.nginx hasta completar migración.
"""

# Enforcement: este módulo puede importar atlas.core (contratos, errores).
# NO importar atlas.cli ni otros providers desde aquí.
