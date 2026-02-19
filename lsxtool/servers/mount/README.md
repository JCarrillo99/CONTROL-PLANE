# Módulo de Montajes - LSX Tool

Módulo para gestión de montajes de sistemas de archivos remotos.

## Estructura

```
mount/
├── __init__.py
├── cli.py          # Interfaz CLI con Typer
├── checks.py       # Validaciones (entorno, dependencias, permisos)
├── sshfs.py        # Lógica de montaje SSHFS
└── README.md
```

## Uso

### Montaje SSHFS

```bash
# Montaje interactivo guiado
sudo ./lsxtool-cli servers mount sshfs
```

El comando guiará paso a paso:
1. Verificación de entorno WSL
2. Verificación de dependencias (sshfs, fusermount, sshpass)
3. Solicitud de información del servidor remoto
4. Creación del punto de montaje
5. Ejecución del montaje
6. Verificación post-montaje

## Dependencias

- `sshfs` - Cliente SSHFS
- `fuse` - Sistema de archivos en espacio de usuario (proporciona `fusermount`)
- `sshpass` - Herramienta para pasar contraseñas a SSH (opcional, solo si se usa contraseña)

## Características

- ✅ Verificación automática de entorno WSL
- ✅ Verificación e instalación automática de dependencias
- ✅ Flujo interactivo guiado paso a paso
- ✅ Detección y manejo de montajes existentes
- ✅ Opciones seguras de SSHFS (reconnect, ServerAliveInterval, etc.)
- ✅ Verificación post-montaje
- ✅ Manejo robusto de errores

## Opciones SSHFS

El módulo usa las siguientes opciones por defecto:

- `reconnect` - Reconectar automáticamente en caso de desconexión
- `ServerAliveInterval=15` - Enviar keepalive cada 15 segundos
- `ServerAliveCountMax=3` - Máximo de keepalives fallidos antes de desconectar
- `default_permissions` - Respetar permisos del sistema de archivos remoto
- `cache=yes` - Habilitar caché para mejor rendimiento
- `cache_timeout=60` - Timeout de caché de 60 segundos

## Seguridad

- Las contraseñas se solicitan usando `getpass` (no se muestran en pantalla)
- Se recomienda usar claves SSH en lugar de contraseñas
- El módulo verifica permisos antes de realizar operaciones

## Extensibilidad

El módulo está diseñado para ser fácilmente extensible con otros tipos de montajes:

- NFS (Network File System)
- CIFS/SMB (Windows shares)
- Otros sistemas de archivos remotos

Para agregar un nuevo tipo de montaje:

1. Crear función similar a `mount_sshfs()` en un nuevo archivo (ej: `nfs.py`)
2. Crear función interactiva similar a `mount_sshfs_interactive()`
3. Agregar comando en `cli.py` usando `@app.command()`
