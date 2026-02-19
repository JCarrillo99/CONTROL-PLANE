"""
Generadores de configuraciones para Traefik, Apache y Nginx
"""

from typing import Optional, Literal


def generate_traefik_config(
    domain: str,
    web_server: Literal["apache", "nginx"],
    web_port: int
) -> str:
    """
    Genera configuración de Traefik para un dominio
    """
    service_name = f"{web_server}-{web_port}-{domain.split('.')[0]}"
    
    # Generar nombre de router (reemplazar puntos y guiones)
    router_name = domain.replace('.', '-').replace('_', '-')
    
    config = f"""# Configuración para {domain} - Traefik 3.4
# Modo LOCAL: Traefik apunta a {web_server.capitalize()} en puerto {web_port}

http:
  routers:
    # Router HTTP - redirige a HTTPS
    {router_name}-http:
      rule: "Host(`{domain}`)"
      service: {service_name}
      entryPoints:
        - web
      middlewares:
        - redirect-to-https
      priority: 100

    # Router HTTPS - servicio principal
    {router_name}-main:
      rule: "Host(`{domain}`)"
      service: {service_name}
      entryPoints:
        - websecure
      middlewares:
        - security-headers
        - compress
      priority: 100
      tls:
        certResolver: letsencrypt

  services:
    # Servicio {web_server.capitalize()} local - Puerto {web_port}
    {service_name}:
      loadBalancer:
        servers:
          - url: "http://localhost:{web_port}"
        passHostHeader: true
        healthCheck:
          path: /
          interval: 30s
          timeout: 5s
          scheme: http
          headers:
            Host: {domain}
"""
    return config


def generate_apache_config(
    domain: str,
    root_path: str,
    app_type: Literal["php", "laravel", "phalcon", "html", "spa"],
    php_version: Optional[str]
) -> str:
    """
    Genera configuración de Apache para un dominio
    """
    site_name = domain.replace('.', '_')
    
    # Ajustar root_path según tipo de aplicación
    if app_type == "laravel":
        document_root = root_path  # Ya viene con /public si es Laravel
    else:
        document_root = root_path
    
    # Configuración PHP-FPM
    php_handler = ""
    if app_type in ("php", "laravel", "phalcon") and php_version:
        php_handler = f"""        # PHP-FPM para PHP {php_version}
        <FilesMatch \\.php$>
            SetHandler "proxy:unix:/var/run/php/php{php_version}-fpm.sock|fcgi://localhost/"
        </FilesMatch>"""
    
    config = f"""# Configuración para {domain} - Apache Puerto 9200

<VirtualHost *:9200>
    ServerName {domain}

    # Logs
    ErrorLog ${{APACHE_LOG_DIR}}/{site_name}-error.log
    CustomLog ${{APACHE_LOG_DIR}}/{site_name}-access.log combined

    # Root de la aplicación
    DocumentRoot {document_root}
    DirectoryIndex index.php index.html index.htm

    # --- Directorio principal ---
    <Directory {document_root}>
        Options -Indexes +FollowSymLinks
        AllowOverride All
        Require all granted
{php_handler}
    </Directory>

    # Archivos estáticos (con caché y tipos MIME correctos)
    <LocationMatch "\\.(css|js|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot|webp)$">
        # Asegurar tipo MIME correcto para CSS
        <If "%{{REQUEST_URI}} =~ /\\.css$/">
            ForceType text/css
        </If>
        # Asegurar tipo MIME correcto para JS
        <If "%{{REQUEST_URI}} =~ /\\.js$/">
            ForceType application/javascript
        </If>
        # Caché para archivos estáticos
        Header set Cache-Control "public, max-age=31536000, immutable"
        ExpiresActive On
        ExpiresDefault "access plus 1 year"
    </LocationMatch>

    # Denegar acceso a archivos sensibles
    <FilesMatch "^(\\.env|\\.git|composer\\.(json|lock)|package\\.json|yarn\\.lock)$">
        Require all denied
    </FilesMatch>
</VirtualHost>
"""
    return config


def generate_nginx_config(
    domain: str,
    root_path: str,
    app_type: Literal["php", "laravel", "phalcon", "html", "spa"],
    php_version: Optional[str],
    port: int
) -> str:
    """
    Genera configuración de Nginx para un dominio
    """
    site_name = domain.replace('.', '-')
    
    # Ajustar root_path según tipo de aplicación
    if app_type == "laravel":
        document_root = f"{root_path}/public"
    else:
        document_root = root_path
    
    # Configuración PHP-FPM
    php_location = ""
    if app_type in ("php", "laravel", "phalcon") and php_version:
        php_location = f"""
    # PHP-FPM
    location ~ \\.php$ {{
        try_files $uri =404;
        fastcgi_split_path_info ^(.+\\.php)(/.+)$;
        fastcgi_pass unix:/var/run/php/php{php_version}-fpm.sock;
        fastcgi_param SCRIPT_FILENAME $realpath_root$fastcgi_script_name;
        fastcgi_index index.php;
        include fastcgi_params;
        
        # Timeouts para PHP
        fastcgi_read_timeout 300s;
        fastcgi_send_timeout 300s;
        fastcgi_connect_timeout 60s;
        
        # Buffers para PHP
        fastcgi_buffer_size 128k;
        fastcgi_buffers 4 256k;
        fastcgi_busy_buffers_size 256k;
    }}"""
    
    # Configuración de ubicación principal
    if app_type == "laravel":
        location_block = """    # Laravel routing
    location / {
        try_files $uri $uri/ /index.php?$query_string;
    }"""
    elif app_type in ("php", "phalcon"):
        location_block = """    location / {
        try_files $uri $uri/ /index.php?$query_string;
    }"""
    else:
        location_block = """    location / {
        try_files $uri $uri/ =404;
    }"""
    
    # Protecciones adicionales para Laravel
    laravel_protections = ""
    if app_type == "laravel":
        laravel_protections = """
    location ~ ^/(storage|vendor|bootstrap/cache) {
        deny all;
        return 404;
    }"""
    
    config = f"""server {{
    listen {port};
    listen [::]:{port};
    server_name {domain};
    
    root {document_root};
    index index.php index.html index.htm;
    
    # ========== SNIPPETS ==========
    
    include /etc/nginx/snippets/server/00-core/01-security/security-server.conf;
    include /etc/nginx/snippets/server/00-core/05-gzip/gzip.conf;
    include /etc/nginx/snippets/server/00-core/02-headers/headers.conf;
    
    # ========== LOGS ==========
    access_log /var/log/nginx/{site_name}-access.log;
    error_log /var/log/nginx/{site_name}-error.log;
    
    # ========== UBICACIONES ==========
    
{location_block}{php_location}
    
    # Denegar acceso a archivos sensibles
    location ~ /\\.(env|git|htaccess) {{
        deny all;
        return 404;
    }}{laravel_protections}
}}
"""
    return config
