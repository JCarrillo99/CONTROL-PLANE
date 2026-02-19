# LSX Tool - CLI Corporativa Unificada

Herramienta CLI interna para gestión de TI, estructurada por departamentos funcionales.

## Estructura

LSX Tool está organizada en módulos por departamento:

- **networks** - Gestión de Redes y DNS
- **servers** - Gestión de Servidores Web (Nginx, Apache, Traefik)
- **devops** - Herramientas DevOps (CI/CD, Jenkins, GitLab)
- **infra** - Gestión de Infraestructura (monitoreo, backups, salud)

## Instalación

```bash
cd lsxtool
./setup_cli.sh
```

## Uso General

```bash
# Ver ayuda general
./lsxtool-cli --help

# Ver información sobre LSX Tool
./lsxtool-cli info

# Ver versión
./lsxtool-cli version
```

## Módulo Networks

Gestión de DNS y configuración de red.

```bash
# Configurar DNS Normal/Público
sudo ./lsxtool-cli networks dns config normal

# Configurar DNS Corporativo
sudo ./lsxtool-cli networks dns config corp

# Ver estado actual
./lsxtool-cli networks dns status

# Validar DNS
./lsxtool-cli networks dns test
./lsxtool-cli networks dns test --host ejemplo.com

# Restaurar desde backup
sudo ./lsxtool-cli networks dns restore
```

## Módulo Servers

Gestión completa de servidores web, sincronización y sitios.

### Estado y Gestión de Servicios

```bash
# Ver estado de todos los servidores y sincronizaciones
./lsxtool-cli servers status

# Gestionar Nginx
./lsxtool-cli servers nginx status
sudo ./lsxtool-cli servers nginx reload
sudo ./lsxtool-cli servers nginx restart
sudo ./lsxtool-cli servers nginx test

# Gestionar Apache
./lsxtool-cli servers apache status
sudo ./lsxtool-cli servers apache reload
sudo ./lsxtool-cli servers apache restart
sudo ./lsxtool-cli servers apache test

# Gestionar Traefik
./lsxtool-cli servers traefik status
sudo ./lsxtool-cli servers traefik reload
sudo ./lsxtool-cli servers traefik restart
```

### Sincronización de Configuraciones

```bash
# Sincronización interactiva
sudo ./lsxtool-cli servers sync

# Sincronizar servicios específicos
sudo ./lsxtool-cli servers sync traefik
sudo ./lsxtool-cli servers sync apache
sudo ./lsxtool-cli servers sync nginx
sudo ./lsxtool-cli servers sync all
```

### Gestión de Sitios

```bash
# Listar todos los sitios configurados
./lsxtool-cli servers sites list

# Ver estado de los sitios
./lsxtool-cli servers sites status

# Crear un nuevo sitio (interactivo)
sudo ./lsxtool-cli servers sites create
```

## Módulo DevOps

Herramientas DevOps (en desarrollo).

```bash
# Ver estado
./lsxtool-cli devops status

# CI/CD
./lsxtool-cli devops ci status
./lsxtool-cli devops ci list

# Jenkins
./lsxtool-cli devops jenkins status
./lsxtool-cli devops jenkins jobs
./lsxtool-cli devops jenkins build --job nombre-job

# GitLab
./lsxtool-cli devops gitlab status
./lsxtool-cli devops gitlab projects
./lsxtool-cli devops gitlab pipelines
```

## Módulo Infra

Gestión de infraestructura.

```bash
# Ver estado general
./lsxtool-cli infra status

# Monitoreo
./lsxtool-cli infra monitoring status
./lsxtool-cli infra monitoring metrics

# Backups
./lsxtool-cli infra backup status
./lsxtool-cli infra backup list
./lsxtool-cli infra backup create

# Salud del sistema
./lsxtool-cli infra health
```

## Arquitectura

```
lsxtool/
├── cli.py                 # CLI principal (registra submódulos)
├── networks/
│   ├── __init__.py
│   ├── cli.py            # Comandos de redes
│   └── dns_manager.py    # Lógica DNS
├── servers/
│   ├── __init__.py
│   ├── cli.py            # Comandos de servidores
│   ├── apache/           # Configuraciones Apache
│   ├── nginx/            # Configuraciones Nginx
│   ├── traefik/          # Configuraciones Traefik
│   └── cli_modules/      # Módulos de gestión
│       ├── __init__.py
│       ├── sync.py       # Sincronización de configuraciones
│       ├── site_creator.py  # Creación de sitios
│       └── config_generators.py  # Generadores de configuración
├── devops/
│   ├── __init__.py
│   └── cli.py            # Comandos DevOps
├── infra/
│   ├── __init__.py
│   └── cli.py            # Comandos infraestructura
├── requirements.txt
├── setup_cli.sh
└── README.md
```

## Características

- ✅ Estructura modular por departamento
- ✅ CLI unificada con subcomandos
- ✅ Interfaz visual con Rich
- ✅ Código tipado y fácil de auditar
- ✅ Separación clara de responsabilidades
- ✅ Fácil de extender con nuevos comandos
- ✅ Manejo robusto de errores
- ✅ Gestión completa de servidores web
- ✅ Sincronización automática de configuraciones
- ✅ Creación interactiva de sitios

## Migración desde server-cli

La funcionalidad de `server-cli` ha sido integrada en `lsxtool servers`:

- `server-cli sync` → `lsxtool-cli servers sync`
- `server-cli create` → `lsxtool-cli servers sites create`
- `server-cli status` → `lsxtool-cli servers status`
- `server-cli list-sites` → `lsxtool-cli servers sites list`

Los archivos antiguos (`cli.py`, `server-cli`, `cli_modules/`) han sido movidos/eliminados.

## Extensión

Para agregar nuevos comandos a un departamento:

1. Edita el archivo `cli.py` del departamento correspondiente
2. Agrega el nuevo comando con `@app.command()`
3. Implementa la lógica en funciones separadas
4. El comando estará disponible automáticamente

## Notas Técnicas

- Cada departamento es un módulo independiente con su propio `cli.py`
- Los módulos se registran en el CLI principal usando `app.add_typer()`
- El CLI usa un entorno virtual (venv) para dependencias
- Los comandos que modifican configuración requieren permisos de root
- El wrapper `lsxtool-cli` maneja automáticamente el venv
