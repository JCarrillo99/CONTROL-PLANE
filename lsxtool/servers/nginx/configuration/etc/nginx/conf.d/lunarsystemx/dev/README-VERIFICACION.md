# Verificación de Configuración Nginx - Lunar System X DEV

## 📋 Archivos de Configuración

### CORE APIs
1. `dev-identity.lunarsystemx.com.conf` → Puerto 3001 (NestJS)
2. `dev-platform.lunarsystemx.com.conf` → Puerto 3002 (NestJS)
3. `dev-intelligence.lunarsystemx.com.conf` → Puerto 8002 (FastAPI)

### FRONTEND (Next.js Multi-tenant)
4. `dev-capaing.lunarsystemx.com.conf`
5. `dev-innovanista.lunarsystemx.com.conf` 

### TENANT APIs
6. `api.dev-capaing.lunarsystemx.com.conf` 

## ✅ Comandos de Validación y Recarga

### 1. Validar Sintaxis de Nginx

```bash
# Validar configuración sin aplicar cambios
sudo nginx -t

# Salida esperada:
# nginx: the configuration file /etc/nginx/nginx.conf syntax is ok
# nginx: configuration file /etc/nginx/nginx.conf test is successful
```

### 2. Recargar Nginx (sin downtime)

```bash
# Recargar configuración manteniendo conexiones activas
sudo systemctl reload nginx

# O alternativamente:
sudo nginx -s reload
```

### 3. Reiniciar Nginx (si reload no funciona)

```bash
# Reinicio completo (corta conexiones activas)
sudo systemctl restart nginx
```

### 4. Verificar Estado de Nginx

```bash
# Estado del servicio
sudo systemctl status nginx

# Verificar que está escuchando en puerto 9200
sudo ss -tlnp | grep :9200
```

## 🧪 Verificación con cURL

### CORE APIs

```bash
# Identity
curl -v -H "Host: dev-identity.lunarsystemx.com" http://127.0.0.1/

# Platform
curl -v -H "Host: dev-platform.lunarsystemx.com" http://127.0.0.1:9200/

# Intelligence
curl -v -H "Host: dev-intelligence.lunarsystemx.com" http://127.0.0.1:9200/
```

### FRONTEND

```bash
# Capaing
curl -v -H "Host: dev-capaing.lunarsystemx.com" http://127.0.0.1:9200/

# Innovanista
curl -v -H "Host: dev-innovanista.lunarsystemx.com" http://127.0.0.1:9200/
```

### TENANT API

```bash
# API Capaing
curl -v -H "Host: api.dev-capaing.lunarsystemx.com" http://127.0.0.1:9200/

# Documentación FastAPI
curl -v -H "Host: api.dev-capaing.lunarsystemx.com" http://127.0.0.1:9200/docs
curl -v -H "Host: api.dev-capaing.lunarsystemx.com" http://127.0.0.1:9200/redoc
```

### Verificar Headers de Proxy

```bash
# Verificar que los headers X-Forwarded-* se están pasando correctamente
curl -v http://dev-identity.lunarsystemx.com 2>&1 | grep -i "forwarded\|real-ip"

# O con más detalle:
curl -v http://dev-identity.lunarsystemx.com
```

### Verificar desde Windows (si hosts está configurado)

```powershell
# Desde PowerShell en Windows
curl http://dev-identity.lunarsystemx.com
curl http://dev-platform.lunarsystemx.com
curl http://dev-intelligence.lunarsystemx.com
curl http://dev-capaing.lunarsystemx.com
curl http://dev-innovanista.lunarsystemx.com
curl http://api.dev-capaing.lunarsystemx.com
curl http://api.dev-capaing.lunarsystemx.com/docs

# Verificar directamente el puerto 9200 de Nginx (bypass Traefik)
curl -H "Host: dev-identity.lunarsystemx.com" http://172.20.70.169:9200/
```

## 📊 Verificación de Logs

### Ver logs en tiempo real

```bash
# CORE APIs
sudo tail -f /var/log/nginx/dev-identity-access.log
sudo tail -f /var/log/nginx/dev-platform-access.log
sudo tail -f /var/log/nginx/dev-intelligence-access.log

# FRONTEND
sudo tail -f /var/log/nginx/dev-capaing-access.log
sudo tail -f /var/log/nginx/dev-innovanista-access.log

# TENANT API
sudo tail -f /var/log/nginx/api-dev-capaing-access.log

# Logs de error
sudo tail -f /var/log/nginx/dev-identity-error.log
sudo tail -f /var/log/nginx/dev-platform-error.log
sudo tail -f /var/log/nginx/dev-intelligence-error.log
sudo tail -f /var/log/nginx/dev-capaing-error.log
sudo tail -f /var/log/nginx/dev-innovanista-error.log
sudo tail -f /var/log/nginx/api-dev-capaing-error.log
```

### Buscar errores específicos

```bash
# Buscar errores 502 (Bad Gateway - app no responde)
sudo grep "502" /var/log/nginx/dev-identity-error.log

# Buscar errores de conexión
sudo grep "connect() failed" /var/log/nginx/dev-identity-error.log

# Ver últimas 50 líneas de error
sudo tail -50 /var/log/nginx/dev-identity-error.log
```

## 🔌 Verificación de Puertos de Aplicaciones

### Verificar que las apps están corriendo

## 🔀 Verificación de Configuración de Traefik

### Archivo de Configuración de Traefik

El archivo de configuración de Traefik está en:
```
traefik/config/dynamic/http/dev-lunarsystemx-domains.yml
```

Este archivo enruta todos los dominios DEV de lunarsystemx a Nginx en puerto 9200.

### Verificar que Traefik está enrutando correctamente

```bash
# Ver logs de Traefik (si está corriendo)
docker logs traefik 2>&1 | grep -i "lunarsystemx"

# O si Traefik está como servicio:
sudo journalctl -u traefik -f | grep -i "lunarsystemx"

# Verificar que Traefik detectó la configuración
docker logs traefik 2>&1 | grep -i "dev-lunarsystemx-domains"
```

### Recargar Traefik (si es necesario)

```bash
# Si Traefik está en Docker
docker restart traefik

# O si Traefik está como servicio
sudo systemctl reload traefik
```

## ✅ Checklist de Verificación

### Pre-requisitos
- [ ] Archivos de Nginx sincronizados a `/etc/nginx/conf.d/lunarsystemx/dev/`
- [ ] `nginx -t` pasa sin errores
- [ ] Nginx se recarga correctamente (`systemctl reload nginx`)
- [ ] Nginx está escuchando en puerto 9200
- [ ] Archivo de Traefik `dev-lunarsystemx-domains.yml` creado y apunta a puerto 9200
- [ ] Traefik está corriendo y detectó la configuración
- [ ] Archivo hosts de Windows configurado apuntando a `172.20.70.169`

### Aplicaciones
- [ ] Identity corriendo 
- [ ] Platform corriendo 
- [ ] Intelligence corriendo 
- [ ] Next.js corriendo 
- [ ] API Capaing corriendo 

### Verificación de Rutas
- [ ] cURL desde WSL funciona con headers Host para todos los dominios
- [ ] cURL desde Windows funciona (si hosts está configurado)
- [ ] Los logs de acceso muestran requests entrantes
- [ ] No hay errores en los logs de error
- [ ] `/docs` y `/redoc` funcionan en `api.dev-capaing.lunarsystemx.com`

### Traefik
- [ ] Traefik está enrutando correctamente a Nginx
- [ ] Los dominios resuelven correctamente desde Windows

## 🐛 Troubleshooting Común

### Error: "502 Bad Gateway"
- **Causa**: La aplicación no está corriendo o no está en el puerto esperado
- **Solución**: 
  ```bash
  # Verificar que la app está corriendo
  sudo ss -tlnp | grep :3001
  # Verificar logs de la aplicación
  ```

### Error: "Connection refused"
- **Causa**: Nginx no puede conectar a la aplicación
- **Solución**: Verificar que la app está escuchando en `127.0.0.1` y no solo en `localhost`

### Error: "No route to host"
- **Causa**: Problema de red o firewall
- **Solución**: Verificar que no hay firewall bloqueando conexiones locales

### El dominio no resuelve
- **Causa**: El archivo hosts de Windows no está configurado o apunta a IP incorrecta
- **Solución**: Verificar `C:\Windows\System32\drivers\etc\hosts` apunta a `172.20.70.169`

### Next.js muestra error de tenant
- **Causa**: Next.js no está configurado para manejar el dominio
- **Solución**: Verificar configuración multi-tenant de Next.js

### FastAPI /docs no carga
- **Causa**: Problema con headers o CORS
- **Solución**: Verificar que los headers `Host` se están pasando correctamente

## 📝 Notas Importantes

1. **IP de WSL**: `172.20.70.169` - Asegúrate de que el archivo hosts de Windows apunta a esta IP
2. **Puertos de Apps**: Las aplicaciones deben estar corriendo ANTES de que Nginx pueda hacer proxy
3. **Traefik**: Traefik debe estar configurado para enrutar estos dominios a Nginx en puerto 80
4. **Logs**: Los logs se guardan en `/var/log/nginx/` con nombres específicos por dominio
5. **Multi-tenancy**: Next.js maneja múltiples tenants basándose en el header `Host`
6. **Arquitectura**: Esta configuración refleja exactamente la arquitectura de PROD, solo cambia el prefijo `dev-`
