# Sistema Declarativo de Infraestructura

Sistema orquestador estilo Terraform/Kubernetes para `lsxtool`. La fuente de verdad son archivos YAML en `.lsxtool/`, no los archivos `.conf` (que son artefactos generados).

## 🎯 Principios Fundamentales

1. **YAML es la fuente de verdad**: Los `.conf` son artefactos generados que pueden borrarse y recrearse
2. **Modular**: Un root (`lsx.yaml`) + múltiples archivos especializados
3. **Reconstrucción total**: El sistema puede reconstruir todo el entorno desde cero
4. **Drift detection**: Detecta diferencias entre estado deseado (YAML) y real (.conf)

## 📁 Estructura

```
.lsxtool/
├── lsx.yaml                # ROOT ORQUESTADOR
├── globals.yaml            # defaults y convenciones
├── providers/
│   ├── lsx.yaml
│   ├── stic.yaml
│   └── external.yaml
├── servers/
│   ├── srvecnom-dev.yaml
│   └── srvecnom-prod.yaml
├── domains/
│   ├── dev-identity.lunarsystemx.com.yaml
│   └── api.lunarsystemx.com.yaml
└── services/
    ├── identity-api.yaml
    └── citas-api.yaml
```

## 🚀 Comandos

### Bootstrap (PATCH mode)
```bash
lsxtool servers bootstrap nginx dev-identity.lunarsystemx.com
```
- Lee YAML primero
- Solo pregunta campos faltantes
- NO pregunta: dominio, slug, tipo, upstream (si ya están en YAML)
- Guarda en YAML + .conf

### Reconfigure (FULL mode)
```bash
lsxtool servers reconfigure nginx dev-identity.lunarsystemx.com
```
- Ignora valores previos
- Pide TODOS los campos
- Sobrescribe YAML + .conf

### Apply (Reconciliación)
```bash
lsxtool servers apply                                    # Aplica todo
lsxtool servers apply domains/dev-identity.lunarsystemx.com.yaml
lsxtool servers apply dev-identity.lunarsystemx.com
```
- Compara estado deseado (YAML) vs real (.conf)
- Corrige automáticamente
- Regenera .conf desde YAML

### Drift Detection
```bash
lsxtool servers drift detect
lsxtool servers drift detect --domain dev-identity.lunarsystemx.com
```
- Detecta diferencias entre YAML y .conf
- Muestra tabla de drift
- Sugiere ejecutar `apply` para reconciliar

### Migrate (Legacy → Declarativo)
```bash
lsxtool servers migrate              # Migra todo
lsxtool servers migrate --dry-run    # Solo muestra qué se migraría
```
- Convierte .conf existentes → YAML
- Respeta configuraciones ya migradas

## 📝 Ejemplo de Domain YAML

```yaml
domain: dev-identity.lunarsystemx.com
type: subdomain
slug: identity
environment: dev
provider: LSX
server: srvecnom-dev

backend:
  type: nginx
  root: /var/www/identity
  listen_port: 9100
  upstream:
    service_type: api
    tech: node
    tech_version: 20.x
    tech_provider: volta
    tech_manager: yarn
    port: 3001

owner: equipo-desarrollo
description: API de identidad (NestJS)
```

## 🔄 Flujo de Trabajo

1. **Primera vez**: `bootstrap` crea YAML + .conf
2. **Modificaciones**: Editar YAML directamente o usar `reconfigure`
3. **Aplicar cambios**: `apply` regenera .conf desde YAML
4. **Detectar drift**: `drift detect` muestra diferencias
5. **Reconstrucción**: Borrar `.conf`, ejecutar `apply` → todo se regenera

## 🧠 Compatibilidad Legacy

El sistema mantiene compatibilidad con `.conf` existentes:
- `bootstrap` lee YAML primero, luego enriquece desde .conf legacy
- `migrate` convierte .conf → YAML automáticamente
- Los `.conf` siguen funcionando mientras se migra
