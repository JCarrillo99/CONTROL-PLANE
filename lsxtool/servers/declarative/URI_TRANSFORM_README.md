# Transformación URI en LSXTOOL

## Problema

Las aplicaciones **no siempre viven en el mismo path** que el proxy público expone.

**Ejemplo:**
- Usuario accede: `https://dev-identity.lunarsystemx.com/api/identity/`
- Aplicación NestJS espera: `http://192.168.20.234:3001/` (no `/api/identity/`)

Antes esto causaba **404** porque NGINX reenviaba la URI completa al backend.

---

## Solución: URI Explícito en YAML

Cada `route` tipo `proxy` incluye una sección `uri`:

```yaml
uri:
  public: /api/identity/    # Path público (NGINX location)
  upstream: /                # Path real que espera la app
  strategy: strip            # strip | passthrough
```

---

## Estrategias

### 1. `strategy: strip`

**Usa:** cuando la app **NO espera** el prefijo público.

**Genera:**
```nginx
location /api/identity/ {
    rewrite ^/api/identity/?(.*)$ /$1 break;
    proxy_pass http://api__identity;
}
```

**Efecto:**
- `GET /api/identity/` → backend recibe `GET /`
- `GET /api/identity/auth` → backend recibe `GET /auth`
- `GET /api/identity/users/123` → backend recibe `GET /users/123`

---

### 2. `strategy: passthrough`

**Usa:** cuando la app **SÍ espera** el path público completo.

**Genera:**
```nginx
location /api/ {
    proxy_pass http://backend/api/;
}
```

**Efecto:**
- `GET /api/users` → backend recibe `GET /api/users`
- La URI se reenvía tal cual.

---

## YAML Completo

```yaml
domain: dev-identity.lunarsystemx.com
role: frontend
environment: dev
provider: lunarsystemx

server_web:
  type: nginx
  version: "1.26.3"

root:
  path: /mnt/d/www/00-LSX/100-projects/demos/php/frontend
  owner: equipo-identity
  technical_user: michael.carrillo

routes:
  /api/identity/:
    type: proxy
    upstream_ref: api__identity
    uri:
      public: /api/identity/
      upstream: /
      strategy: strip

  /api/demo/:
    type: proxy
    upstream_ref: api__demo
    uri:
      public: /api/demo/
      upstream: /
      strategy: strip

  /:
    type: proxy
    upstream_ref: frontend__php_demo
    uri:
      public: /
      upstream: /
      strategy: passthrough
```

---

## Migración de Configs Existentes

Ejecuta el script de migración:

```bash
cd /home/debian-trixie/servers-install-v2
python3 -m lsxtool.servers.declarative.migrate_uri
```

**Inferencia automática:**
- Para `/api/...` → `strategy: strip`, `upstream: /`
- Para `/` → `strategy: passthrough`, `upstream: /`

**Dry-run:**
```bash
python3 -m lsxtool.servers.declarative.migrate_uri --dry-run
```

---

## Bootstrap Interactivo

Cuando crees un nuevo dominio con `lsxtool servers bootstrap --v2`:

```
Routes (path → upstream + transformación URI):
  uri.public (path público) (/): /api/identity/
  upstream_ref: api__identity
  uri.upstream (path en la app) (/): /
  uri.strategy (strip|passthrough) (strip): 
```

**Defaults inteligentes:**
- `public != /` → `upstream=/`, `strategy=strip`
- `public == /` → `upstream=/`, `strategy=passthrough`

---

## Reglas de Oro

1. ✅ **Siempre define `uri`** explícitamente en nuevas configs
2. ✅ **`public`** → path que ve el usuario en el navegador
3. ✅ **`upstream`** → path que espera la aplicación backend
4. ✅ **`strategy: strip`** → cuando backend NO espera el prefijo
5. ✅ **`strategy: passthrough`** → cuando backend SÍ lo necesita
6. ✅ **Múltiples routes** pueden apuntar al mismo `upstream_ref`
7. ❌ **Nunca asumas** que `public == upstream`

---

## Testing

```bash
# Regenerar conf desde YAML
python3 -c "
from pathlib import Path
from lsxtool.servers.declarative.loader_v2 import load_domain
from lsxtool.servers.declarative.generator_v2 import generate_nginx_config_v2
from lsxtool.servers.declarative.convention_v2 import find_site_path_for_domain

base = Path('.')
domain = 'dev-identity.lunarsystemx.com'
cfg = load_domain(base, domain)
_, prov, env = find_site_path_for_domain(base, domain)
ng = generate_nginx_config_v2(base, cfg, prov, env)
print(ng)
"
```

---

## Usuario Técnico por Defecto

Cuando `technical_user` no está especificado:
- Default: `michael.carrillo`
- Se usa en permisos de `root` y `logs`
