# ATLAS – Control Plane (LSX Tool)

ATLAS es el módulo de **Control Plane** de LSX Tool: separa responsabilidades en capas y deja el estado fuera del código.

## Capas

| Capa | Responsabilidad | Restricción |
|------|-----------------|-------------|
| **core** | Lógica pura: modelos, validación, planners, contratos | No importa cli, providers ni filesystem real |
| **cli** | Traduce comandos → llamadas al core | No contiene lógica de negocio |
| **api** | (Futura) REST/otro protocolo sobre el mismo core | Solo traduce peticiones → core |
| **desktop** | (Futuro) UI sobre el mismo core | — |
| **providers** | Plugins de infra: nginx, apache, traefik, dns, servers | Implementan contratos del core; no ejecutan lógica directa |

## Estado y runtime

- **El estado y el runtime no viven dentro del repo.**
- Directorio canónico: **`/var/lib/lsx/atlas/`**
- Para compatibilidad con flujos actuales, se sigue soportando estado en el proyecto (`.lsxtool/`) vía `LSXTOOL_DEV` o detección de repo; la migración gradual debe tender a usar solo `/var/lib/lsx/atlas/`.

## Estructura

```
atlas/
├── core/           # Lógica agnóstica de interfaz
│   ├── project/     # models, validator, planner, detector
│   ├── runtime/     # resolver (rutas estado), state (contratos)
│   ├── infra/       # base.py, contracts.py
│   └── errors.py
├── cli/             # app.py (composición de comandos)
├── providers/       # nginx, apache, traefik, dns, servers
├── api/             # (vacío, preparado)
├── desktop/         # (placeholder futuro)
├── contracts/       # schemas.yaml
├── __main__.py
└── README.md
```

## Uso

- **Mismo CLI que antes:** `python -m lsxtool` o el script que apunte a `lsxtool/cli.py` (ahora delega a ATLAS).
- **Ejecutar como módulo:** `python -m atlas`

Los comandos (`lsxtool networks ...`, `lsxtool servers ...`, etc.) no cambian; solo el wiring interno pasa por ATLAS.

## Reglas de arquitectura

1. **Core:** no puede importar nada de `cli`, `infra` (providers), scripts ni filesystem real; solo lógica pura y contratos.
2. **CLI:** solo traduce comandos a llamadas al core (o a lsxtool mientras se migra).
3. **Providers:** dependen del core (contratos); el core no depende de ellos.
4. **Estado:** documentado y, en objetivo, en `/var/lib/lsx/atlas/`.
