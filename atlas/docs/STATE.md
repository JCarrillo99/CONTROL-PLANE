# Estado y runtime de ATLAS

## Dónde vive el estado

El estado del Control Plane **no debe vivir dentro del repositorio**. Debe escribirse y leerse desde:

```
/var/lib/lsx/atlas/
```

Ahí deben residir (en migración gradual):

- Estado declarativo (equivalente a lo que hoy está en `.lsxtool/` en el proyecto)
- Cache y runtime que el Control Plane necesite
- Configuración por entorno que no sea código

## Compatibilidad actual

Hoy el código sigue soportando:

- **Proyecto (desarrollo):** `.lsxtool/` en la raíz del repo, con `LSXTOOL_DEV=1` o detección automática.
- **Usuario (producción):** `~/.lsxtool/` (o el home efectivo con `sudo`).

El módulo `atlas.core.runtime.resolver` expone:

- **`state_root()`** → `/var/lib/lsx/atlas` (canónico)
- **`project_base()`** → directorio del proyecto si existe (para compatibilidad)

Los comandos actuales no se rompen; la intención es que, con el tiempo, el estado se consolide en `/var/lib/lsx/atlas/` y las interfaces (CLI/API) usen solo el resolver del core para saber dónde leer/escribir.
