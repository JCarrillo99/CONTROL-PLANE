# Optimización de PHP-FPM para dev-recibonomina.yucatan.gob.mx

## Problema Identificado

La aplicación Laravel tarda ~1.7-3 segundos en la primera carga debido a:
1. **Cold start de Laravel**: Carga de autoloader, configuración, etc.
2. **PHP-FPM conservador**: Configuración actual tiene solo 5 max_children
3. **Falta de procesos pre-cargados**: min_spare_servers = 1 es muy bajo

## Configuración Actual PHP-FPM

```
pm.max_children = 5
pm.start_servers = 2
pm.min_spare_servers = 1
pm.max_spare_servers = 3
```

## Optimizaciones Recomendadas

### 1. Aumentar Procesos Pre-cargados

Editar `/etc/php/7.4/fpm/pool.d/www.conf`:

```ini
# Aumentar procesos para mejor rendimiento
pm = dynamic
pm.max_children = 20          # Aumentar de 5 a 20
pm.start_servers = 5          # Aumentar de 2 a 5 (procesos al inicio)
pm.min_spare_servers = 3      # Aumentar de 1 a 3 (mínimo esperando)
pm.max_spare_servers = 8      # Aumentar de 3 a 8 (máximo esperando)
pm.max_requests = 500         # Reciclar procesos después de N requests
pm.process_idle_timeout = 10s # Tiempo antes de matar procesos idle
```

### 2. Optimizar Timeouts

```ini
# Timeout para requests largas
request_terminate_timeout = 300s
```

### 3. Mejorar Rendimiento de Laravel (Aplicación)

```bash
# En la aplicación Laravel:
php artisan config:cache      # Cachear configuración
php artisan route:cache       # Cachear rutas
php artisan view:cache        # Cachear vistas
php artisan optimize          # Optimizar autoloader
```

### 4. Habilitar OPcache en PHP

Verificar que OPcache esté habilitado en `/etc/php/7.4/fpm/php.ini`:

```ini
opcache.enable=1
opcache.memory_consumption=128
opcache.interned_strings_buffer=8
opcache.max_accelerated_files=10000
opcache.revalidate_freq=2
opcache.fast_shutdown=1
```

## Comandos para Aplicar

```bash
# 1. Editar configuración PHP-FPM
sudo nano /etc/php/7.4/fpm/pool.d/www.conf

# 2. Reiniciar PHP-FPM
sudo systemctl restart php7.4-fpm

# 3. Verificar que está corriendo
sudo systemctl status php7.4-fpm

# 4. Optimizar Laravel (desde el directorio de la app)
cd /mnt/d/www/01-STIC/web/recibonomina/app
php artisan config:cache
php artisan route:cache
php artisan view:cache
```

## Resultado Esperado

- **Primera carga**: Reducir de ~3s a ~1.5s
- **Cargas subsecuentes**: Mantener ~0.1-0.2s
- **Mejor manejo de concurrencia**: Más procesos disponibles

## Notas Importantes

- Aumentar `max_children` consume más memoria
- Monitorear uso de memoria: `free -h` y `htop`
- Ajustar según recursos disponibles del servidor
- En producción, considerar valores más altos según carga esperada
