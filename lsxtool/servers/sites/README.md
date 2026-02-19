# Módulo de Gestión de Sitios - Enterprise

Este módulo proporciona una vista operativa y enterprise de los sitios web configurados, integrando información de Traefik con Service Manifests.

## Arquitectura

### Service Manifests
Los Service Manifests son archivos JSON que almacenan metadatos completos de cada sitio, independientes de la configuración de Traefik. Se almacenan en `~/.lsxtool/sites/manifests/`.

### Componentes

- **`manifest.py`**: Gestión de Service Manifests (crear, cargar, guardar, inferir)
- **`traefik_parser.py`**: Parser de configuraciones YAML de Traefik
- **`sites_manager.py`**: Integración de Traefik + Manifests, proporciona `SiteInfo`
- **`cli.py`**: Comandos CLI (actualmente integrado en `servers/cli.py`)

## Comandos

### `lsxtool servers sites list`
Vista resumida operativa. Muestra:
- Dominio
- Proveedor (STIC, LSX, EXTERNAL)
- Ambiente (DEV, QA, PROD)
- Backend (Apache, Nginx)
- Target (host:port)
- Dueño/Equipo

### `lsxtool servers sites list --full`
Vista completa enterprise. Incluye además:
- Tipo de servicio (web, api, admin, static)
- Versión del backend
- Ruta en servidor (DocumentRoot/root)
- Tags

### `lsxtool servers sites info <domain>`
Ficha técnica detallada de un sitio específico. Muestra:
- Información principal (dominio, proveedor, ambiente, tipo, dueño)
- Información técnica (backend, versión, target, ruta)
- Configuración Traefik (referencia secundaria)
- Health check (si está configurado)

### `lsxtool servers sites status`
Estado operativo de todos los sitios (servicios activos/inactivos)

## Inferencia Automática

Si un sitio no tiene manifest, el sistema lo infiere automáticamente desde:
1. Configuración de Traefik (backend type, target)
2. Archivos de configuración de Apache/Nginx (ruta real)
3. Dominio (proveedor, ambiente)

Los manifests inferidos se guardan automáticamente para futuras referencias.

## Extensibilidad

El sistema está diseñado para crecer hacia:
- Health checks automáticos
- SLA y métricas
- Observabilidad (logs, métricas)
- Multi-cluster
- Integración con sistemas de monitoreo

## Estructura de Manifest

```json
{
  "domain": "dev-registroentidad.yucatan.gob.mx",
  "provider": "STIC",
  "service_type": "web",
  "backend_type": "apache",
  "backend_version": "8.3",
  "target": "localhost:9200",
  "path": "/mnt/d/www/01-STIC/web/registroentidad/app",
  "owner": "Equipo Desarrollo",
  "environment": "dev",
  "description": "Sistema de registro de entidades",
  "tags": ["php", "laravel"],
  "health_check_enabled": true,
  "health_check_path": "/health",
  "created_at": "2026-01-27T10:00:00",
  "updated_at": "2026-01-27T10:00:00"
}
```
