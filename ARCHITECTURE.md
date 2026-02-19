# Arquitectura CONTROL-PLANE (ATLAS)

Este repositorio implementa **ATLAS** como Control Plane de LSX Tool, con capas bien separadas y estado fuera del código.

## Capas

| Capa | Ubicación | Responsabilidad |
|------|-----------|-----------------|
| **Core** | `atlas/core/` | Lógica pura: modelos, validación, planners, contratos. No importa CLI ni providers. |
| **CLI** | `atlas/cli/` | Traduce comandos a llamadas al core (y a lsxtool mientras se migra). |
| **API** | `atlas/api/` | Reservado para API REST futura. |
| **Desktop** | `atlas/desktop/` | Reservado para UI futura. |
| **Providers** | `atlas/providers/` | Plugins de infra (nginx, apache, traefik, dns, servers). Dependen del core. |

## Wiring actual

- **Entrada:** `python -m lsxtool`, `python -m atlas`, o ejecutar `lsxtool/cli.py`. Todos delegan a `atlas.cli.app`.
- **Comandos:** Los subcomandos (`networks`, `servers`, `devops`, `infra`, `providers`) siguen en `lsxtool`; la app se compone en `atlas/cli/app.py`. Sin cambios de comportamiento para el usuario.

## Estado y runtime

- **Canónico:** `/var/lib/lsx/atlas/` (documentado en `atlas/docs/STATE.md`).
- **Compatibilidad:** Sigue soportándose `.lsxtool/` en el proyecto y `~/.lsxtool/` vía variables de entorno.

## Reglas de imports

- **core:** No debe importar `atlas.cli`, `atlas.providers.*` ni código que use filesystem real (salvo el resolver de rutas).
- **cli / providers:** Pueden importar desde `atlas.core` y desde `lsxtool` (implementación actual).

Ver también: `atlas/README.md`, `atlas/docs/STATE.md`.
