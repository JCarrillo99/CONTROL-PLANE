# CORS: permitir header `Application-Id` en apistic.yucatan.gob.mx

## Error

```
Access to XMLHttpRequest at 'https://apistic.yucatan.gob.mx/...' from origin 'https://dev-cultura-v2.yucatan.gob.mx' 
has been blocked by CORS policy: Request header field application-id is not allowed by Access-Control-Allow-Headers in preflight response.
```

El frontend envía el header `application-id` y el servidor de la API no lo incluye en `Access-Control-Allow-Headers`, por eso el navegador bloquea la petición.

## Solución: configurar el servidor de apistic.yucatan.gob.mx

Hay que incluir **`Application-Id`** (y, si aplica, **`application-id`**) en la cabecera `Access-Control-Allow-Headers` en las respuestas CORS (sobre todo en la respuesta al preflight OPTIONS).

### Opción A – Apache (mod_headers)

En el VirtualHost o en un `.htaccess` del directorio de la API:

```apache
# CORS: permitir origen y cabeceras necesarias
Header always set Access-Control-Allow-Origin "https://dev-cultura-v2.yucatan.gob.mx"
Header always set Access-Control-Allow-Methods "GET, POST, OPTIONS, PUT, DELETE"
Header always set Access-Control-Allow-Headers "Origin, Content-Type, Accept, Authorization, Application-Id, application-id"
Header always set Access-Control-Allow-Credentials "true"
Header always set Access-Control-Max-Age "100"

# Responder OPTIONS sin pasar a PHP
RewriteEngine On
RewriteCond %{REQUEST_METHOD} OPTIONS
RewriteRule ^ - [R=204,L]
```

Si la API debe aceptar varios orígenes, se puede usar una lista o una lógica por entorno (por ejemplo con `SetEnvIf` y `Header merge`).

### Opción B – PHP (antes de cualquier salida)

En el script que atiende la API (o en un `bootstrap`/`index` común), antes de imprimir nada:

```php
<?php
header('Access-Control-Allow-Origin: https://dev-cultura-v2.yucatan.gob.mx');
header('Access-Control-Allow-Methods: GET, POST, OPTIONS, PUT, DELETE');
header('Access-Control-Allow-Headers: Origin, Content-Type, Accept, Authorization, Application-Id, application-id');
header('Access-Control-Allow-Credentials: true');
header('Access-Control-Max-Age: 100');

if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(204);
    exit;
}
```

Ajusta el `Access-Control-Allow-Origin` si también deben poder llamar otros orígenes (dev, prod, etc.).

### Opción C – Nginx

En el `server` o `location` que sirve la API:

```nginx
add_header Access-Control-Allow-Origin "https://dev-cultura-v2.yucatan.gob.mx" always;
add_header Access-Control-Allow-Methods "GET, POST, OPTIONS, PUT, DELETE" always;
add_header Access-Control-Allow-Headers "Origin, Content-Type, Accept, Authorization, Application-Id, application-id" always;
add_header Access-Control-Allow-Credentials "true" always;
add_header Access-Control-Max-Age "100" always;

if ($request_method = OPTIONS) {
    return 204;
}
```

---

Después de aplicar los cambios, recargar el servidor web (Apache/Nginx) o asegurarse de que el PHP se ejecute con la nueva configuración. No hace falta tocar el frontend en dev-cultura-v2 si la API ya permite el header `application-id`.
