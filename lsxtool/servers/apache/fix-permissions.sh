#!/bin/bash
# Script para corregir permisos de los directorios de configuración de apache

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

CONFIG_DIR="$HOME/servers-install/apache/configuration/etc/apache2"

echo -e "${YELLOW}Corrigiendo permisos de directorios de configuración...${NC}"

# Verificar que se ejecuta como usuario normal (no root)
if [ "$EUID" -eq 0 ]; then
    echo -e "${RED}❌ Este script NO debe ejecutarse como root${NC}"
    echo -e "${YELLOW}Ejecuta: bash $0${NC}"
    exit 1
fi

# Verificar que el directorio existe
if [ ! -d "$CONFIG_DIR" ]; then
    echo -e "${RED}❌ No se encontró el directorio: $CONFIG_DIR${NC}"
    exit 1
fi

# Obtener usuario actual
CURRENT_USER=$(whoami)
CURRENT_GROUP=$(id -gn)

echo -e "${BLUE}Usuario: $CURRENT_USER${NC}"
echo -e "${BLUE}Grupo: $CURRENT_GROUP${NC}"

# Cambiar ownership de todos los directorios de configuración
echo -e "${YELLOW}Cambiando ownership...${NC}"
sudo chown -R "$CURRENT_USER:$CURRENT_GROUP" "$CONFIG_DIR" 2>/dev/null || {
    echo -e "${RED}❌ Error al cambiar ownership. Ejecuta manualmente:${NC}"
    echo -e "${YELLOW}sudo chown -R $CURRENT_USER:$CURRENT_GROUP $CONFIG_DIR${NC}"
    exit 1
}

# Dar permisos de escritura
echo -e "${YELLOW}Estableciendo permisos...${NC}"
sudo chmod -R u+w "$CONFIG_DIR" 2>/dev/null || {
    echo -e "${RED}❌ Error al establecer permisos. Ejecuta manualmente:${NC}"
    echo -e "${YELLOW}sudo chmod -R u+w $CONFIG_DIR${NC}"
    exit 1
}

# Permisos de directorios (755)
find "$CONFIG_DIR" -type d -exec sudo chmod 755 {} \; 2>/dev/null || true

# Permisos de archivos (644)
find "$CONFIG_DIR" -type f -exec sudo chmod 644 {} \; 2>/dev/null || true

echo -e "${GREEN}✅ Permisos corregidos correctamente${NC}"
echo -e "${GREEN}Puedes editar archivos en: $CONFIG_DIR${NC}"

