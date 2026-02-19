#!/bin/bash
# Script de sincronización manual para archivos lunarsystemx
# Ejecutar con: sudo bash sync-manual-lunarsystemx.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONF_SRC="$SCRIPT_DIR/configuration/etc/nginx/conf.d/lunarsystemx"
CONF_DEST="/etc/nginx/conf.d/lunarsystemx"

echo "📁 Sincronizando archivos de configuración de lunarsystemx..."

# Crear directorios si no existen
mkdir -p "$CONF_DEST/dev"
mkdir -p "$CONF_DEST/qa"
mkdir -p "$CONF_DEST/prod"

# Copiar archivo principal
if [ -f "$CONF_SRC/lunarsystemx.conf" ]; then
    cp -f "$CONF_SRC/lunarsystemx.conf" "$CONF_DEST/lunarsystemx.conf"
    chown root:root "$CONF_DEST/lunarsystemx.conf"
    chmod 644 "$CONF_DEST/lunarsystemx.conf"
    echo "✅ lunarsystemx.conf sincronizado"
fi

# Copiar archivos de dev
if [ -d "$CONF_SRC/dev" ]; then
    cp -f "$CONF_SRC/dev"/*.conf "$CONF_DEST/dev/" 2>/dev/null || true
    for file in "$CONF_DEST/dev"/*.conf; do
        if [ -f "$file" ]; then
            chown root:root "$file"
            chmod 644 "$file"
        fi
    done
    echo "✅ Archivos de dev sincronizados"
fi

# Validar configuración
echo "🔍 Validando configuración de Nginx..."
if nginx -t; then
    echo "✅ Configuración válida"
    echo "🔄 Recargando Nginx..."
    systemctl reload nginx
    echo "✅ Nginx recargado"
else
    echo "❌ Error en la configuración de Nginx"
    exit 1
fi

echo "✅ Sincronización completada"
