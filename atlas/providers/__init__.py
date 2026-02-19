"""
Providers: plugins de infraestructura (nginx, apache, traefik, dns, servers).

Implementan atlas.core.infra.contracts; nunca ejecutan lógica directa sin contrato.
El core no importa providers; los providers dependen del core.
"""
