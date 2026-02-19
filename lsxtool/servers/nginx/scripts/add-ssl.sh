#!/bin/bash
# =====================================================
# Script: add-ssl.sh
# Autor: LSX
# Propósito: Agregar SSL a un sitio nginx existente
# =====================================================

set -e

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Directorios
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NGINX_DIR="$(dirname "$SCRIPT_DIR")"
CONF_DIR="$NGINX_DIR/configuration/etc/nginx/conf.d"
PRESETS_DIR="$NGINX_DIR/templates/presets"
SSL_DIR="/etc/nginx/ssl"

echo -e "${GREEN}=========================================="
echo "  AGREGAR SSL A SITIO NGINX"
echo -e "==========================================${NC}\n"

# Verificar root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}❌ Este script debe ejecutarse como root${NC}"
    echo -e "${YELLOW}💡 Ejecuta: sudo $0${NC}"
    exit 1
fi

# Verificar que certbot esté instalado
check_certbot() {
    if ! command -v certbot &>/dev/null; then
        echo -e "${YELLOW}⚠ certbot no está instalado${NC}"
        read -rp "¿Deseas instalar certbot ahora? (S/n): " INSTALL_CERTBOT
        INSTALL_CERTBOT=${INSTALL_CERTBOT:-s}
        
        if [[ "$INSTALL_CERTBOT" =~ ^[Ss]$ ]]; then
            apt-get update -qq
            apt-get install -y certbot python3-certbot-nginx
            echo -e "${GREEN}✔ certbot instalado${NC}"
        else
            echo -e "${YELLOW}⚠ Necesitarás proporcionar certificados manualmente${NC}"
        fi
    fi
}

# Solicitar datos
echo -e "${BLUE}📝 Configuración del dominio:${NC}\n"

read -rp "Dominio (ej: example.com): " DOMAIN
if [ -z "$DOMAIN" ]; then
    echo -e "${RED}❌ El dominio es obligatorio${NC}"
    exit 1
fi

read -rp "Email para Let's Encrypt (ej: admin@$DOMAIN): " EMAIL
EMAIL=${EMAIL:-admin@$DOMAIN}

# Buscar archivo de configuración existente
echo -e "\n${BLUE}🔍 Buscando configuración existente...${NC}"
FOUND_FILES=$(find "$CONF_DIR" -type f -name "*.conf" | grep -v "\.conf\.template" | xargs grep -l "server_name.*$DOMAIN" 2>/dev/null || true)

if [ -z "$FOUND_FILES" ]; then
    echo -e "${RED}❌ No se encontró configuración para: $DOMAIN${NC}"
    echo -e "${YELLOW}💡 Archivos disponibles en conf.d:${NC}"
    find "$CONF_DIR" -type f -name "*.conf" | head -10
    exit 1
fi

SITE_FILE=$(echo "$FOUND_FILES" | head -1)
SITE_DIR=$(dirname "$SITE_FILE")
SITE_NAME=$(basename "$SITE_DIR")

echo -e "${GREEN}✔ Encontrado: $SITE_FILE${NC}"
echo -e "${BLUE}  Carpeta del sitio: $SITE_NAME${NC}\n"

# Extraer información del archivo existente
ROOT_PATH=$(grep -oP '^\s*root\s+\K[^;]+' "$SITE_FILE" | head -1)
INDEX_FILES=$(grep -oP '^\s*index\s+\K[^;]+' "$SITE_FILE" | head -1)
ACCESS_LOG=$(grep -oP '^\s*access_log\s+\K[^;]+' "$SITE_FILE" | head -1)
ERROR_LOG=$(grep -oP '^\s*error_log\s+\K[^;]+' "$SITE_FILE" | head -1)

echo -e "${BLUE}📋 Información del sitio:${NC}"
echo -e "  Root: ${ROOT_PATH:-/var/www/html}"
echo -e "  Index: ${INDEX_FILES:-index.html}"
echo -e "  Access Log: ${ACCESS_LOG:-/var/log/nginx/${SITE_NAME}-access.log}"
echo -e "  Error Log: ${ERROR_LOG:-/var/log/nginx/${SITE_NAME}-error.log}\n"

# Preguntar tipo de certificado
echo -e "${BLUE}🔐 Configuración SSL:${NC}\n"
echo "  1) Generar certificado con Let's Encrypt (certbot)"
echo "  2) Usar certificado existente"
echo "  3) Generar certificado autofirmado (desarrollo)"
echo ""
read -rp "Selecciona opción (1/2/3): " SSL_OPTION

SSL_CERT=""
SSL_KEY=""

case "$SSL_OPTION" in
    1)
        # Let's Encrypt
        check_certbot
        echo -e "\n${BLUE}🔧 Generando certificado con Let's Encrypt...${NC}"
        echo -e "${YELLOW}⚠ Asegúrate que el dominio apunte a este servidor${NC}"
        read -rp "¿Continuar? (s/n): " CONTINUE
        if [[ ! "$CONTINUE" =~ ^[Ss]$ ]]; then
            exit 0
        fi
        
        certbot certonly --nginx -d "$DOMAIN" --email "$EMAIL" --agree-tos --non-interactive || {
            echo -e "${RED}❌ Error al generar certificado${NC}"
            exit 1
        }
        
        SSL_CERT="/etc/letsencrypt/live/$DOMAIN/fullchain.pem"
        SSL_KEY="/etc/letsencrypt/live/$DOMAIN/privkey.pem"
        ;;
    2)
        # Certificado existente
        read -rp "Ruta del certificado (.crt/.pem): " SSL_CERT
        read -rp "Ruta de la clave privada (.key): " SSL_KEY
        
        if [ ! -f "$SSL_CERT" ] || [ ! -f "$SSL_KEY" ]; then
            echo -e "${RED}❌ Los archivos no existen${NC}"
            exit 1
        fi
        ;;
    3)
        # Autofirmado
        echo -e "\n${BLUE}🔧 Generando certificado autofirmado...${NC}"
        mkdir -p "$SSL_DIR/$DOMAIN"
        openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
            -keyout "$SSL_DIR/$DOMAIN/privkey.pem" \
            -out "$SSL_DIR/$DOMAIN/fullchain.pem" \
            -subj "/C=MX/ST=State/L=City/O=Organization/CN=$DOMAIN"
        
        SSL_CERT="$SSL_DIR/$DOMAIN/fullchain.pem"
        SSL_KEY="$SSL_DIR/$DOMAIN/privkey.pem"
        echo -e "${GREEN}✔ Certificado autofirmado creado${NC}"
        ;;
    *)
        echo -e "${RED}❌ Opción inválida${NC}"
        exit 1
        ;;
esac

# Preguntar por redirect
echo ""
read -rp "¿Crear redirect HTTP→HTTPS? (S/n): " CREATE_REDIRECT
CREATE_REDIRECT=${CREATE_REDIRECT:-s}

# Extraer snippets includes del archivo original
SNIPPETS_INCLUDES=$(grep "include /etc/nginx/snippets" "$SITE_FILE" | grep -v "ssl" || true)

# Extraer locations del archivo original
LOCATIONS=$(sed -n '/location/,/^    }/p' "$SITE_FILE" || echo "    location / {\n        try_files \$uri \$uri/ /index.html;\n    }")

# Crear backup
BACKUP_FILE="${SITE_FILE}.bak.$(date +%Y%m%d%H%M%S)"
cp "$SITE_FILE" "$BACKUP_FILE"
echo -e "\n${GREEN}💾 Backup creado: $(basename $BACKUP_FILE)${NC}"

# Generar archivo HTTPS con nombre del dominio
HTTPS_FILE="$SITE_DIR/${DOMAIN}-ssl.conf"
cat > "$HTTPS_FILE" << EOF
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name $DOMAIN;
    
    root ${ROOT_PATH:-/var/www/html};
    index ${INDEX_FILES:-index.html index.htm};
    
    # ========== SSL ==========
    ssl_certificate $SSL_CERT;
    ssl_certificate_key $SSL_KEY;
    
    # Configuración SSL
    include /etc/nginx/snippets/server/00-core/03-ssl/ssl.conf;
    
    # ========== SNIPPETS ==========
$SNIPPETS_INCLUDES
    
    # ========== LOGS ==========
    access_log ${ACCESS_LOG:-/var/log/nginx/${SITE_NAME}-ssl-access.log};
    error_log ${ERROR_LOG:-/var/log/nginx/${SITE_NAME}-ssl-error.log};
    
    # ========== UBICACIONES ==========
$LOCATIONS
}
EOF

echo -e "${GREEN}✔ Archivo HTTPS creado: $HTTPS_FILE${NC}"

# Crear redirect si se solicitó
if [[ "$CREATE_REDIRECT" =~ ^[Ss]$ ]]; then
    REDIRECT_FILE="$SITE_DIR/${DOMAIN}-redirect.conf"
    cat > "$REDIRECT_FILE" << EOF
server {
    listen 80;
    listen [::]:80;
    server_name $DOMAIN;
    
    # Redirect permanente a HTTPS
    return 301 https://\$server_name\$request_uri;
}
EOF
    echo -e "${GREEN}✔ Archivo redirect creado: $REDIRECT_FILE${NC}"
    
    # Renombrar archivo original para que no escuche en puerto 80
    if grep -q "listen 80" "$SITE_FILE"; then
        mv "$SITE_FILE" "${SITE_FILE}.disabled"
        echo -e "${YELLOW}⚠ Archivo HTTP original deshabilitado (renombrado a .disabled)${NC}"
    fi
fi

# Probar configuración
echo -e "\n${BLUE}🧪 Probando configuración de Nginx...${NC}"
sleep 4  # Esperar a que el daemon sincronice

if sudo nginx -t 2>&1 | tee /tmp/nginx-test.log; then
    echo -e "\n${GREEN}✅ Configuración SSL agregada correctamente${NC}"
    echo -e "${BLUE}📁 Archivos creados:${NC}"
    echo -e "  - $(basename $HTTPS_FILE)"
    [[ "$CREATE_REDIRECT" =~ ^[Ss]$ ]] && echo -e "  - $(basename $REDIRECT_FILE)"
    echo ""
    echo -e "${YELLOW}💡 El daemon sincronizará automáticamente en ~3 segundos${NC}"
    echo -e "${YELLOW}💡 Nginx recargará automáticamente si todo está bien${NC}"
    echo ""
    echo -e "${GREEN}🌐 Accede a tu sitio en:${NC}"
    echo -e "  https://$DOMAIN"
else
    echo -e "\n${RED}❌ Error en la configuración${NC}"
    echo -e "${YELLOW}Revirtiendo cambios...${NC}"
    rm -f "$HTTPS_FILE" "$REDIRECT_FILE" 2>/dev/null
    [ -f "${SITE_FILE}.disabled" ] && mv "${SITE_FILE}.disabled" "$SITE_FILE"
    cat /tmp/nginx-test.log
    exit 1
fi

rm -f /tmp/nginx-test.log

