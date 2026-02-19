#!/bin/bash
# Script de desinstalación de Traefik para LunarCore GNU/Linux (Debian Bookworm)

set -e  # Salir si hay algún error

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Variables
TRAEFIK_DIR="/opt/traefik"
TRAEFIK_CONFIG_DIR="/etc/traefik"
TRAEFIK_LOG_DIR="/var/log/traefik"
TRAEFIK_BIN="/usr/local/bin/traefik"
TRAEFIK_USER="traefik"
TRAEFIK_SERVICE="/etc/systemd/system/traefik.service"

echo -e "${RED}=== Desinstalador de Traefik para LunarCore ===${NC}"
echo ""

# Verificar si se ejecuta como root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}❌ Este script debe ejecutarse como root (usa sudo)${NC}"
    exit 1
fi

# Verificar si Traefik está instalado
if [ ! -f "$TRAEFIK_BIN" ]; then
    echo -e "${YELLOW}⚠ Traefik no parece estar instalado${NC}"
    echo "No se encontró $TRAEFIK_BIN"
    exit 0
fi

# Confirmación
echo -e "${YELLOW}⚠ ADVERTENCIA: Esto eliminará completamente Traefik de tu sistema${NC}"
echo ""
echo "Se eliminarán:"
echo "  - Binario: $TRAEFIK_BIN"
echo "  - Configuración: $TRAEFIK_CONFIG_DIR"
echo "  - Logs: $TRAEFIK_LOG_DIR"
echo "  - Servicio systemd: $TRAEFIK_SERVICE"
echo "  - Usuario del sistema: $TRAEFIK_USER"
echo ""
read -p "¿Estás seguro de que deseas continuar? (escribe 'SI' para confirmar): " confirmacion

if [ "$confirmacion" != "SI" ]; then
    echo -e "${GREEN}✓ Operación cancelada${NC}"
    exit 0
fi

echo ""
echo -e "${YELLOW}Iniciando desinstalación...${NC}"
echo ""

# Detener servicio
echo -e "${YELLOW}[1/7]${NC} Deteniendo servicio Traefik..."
if systemctl is-active --quiet traefik; then
    systemctl stop traefik
    echo "  ✓ Servicio detenido"
else
    echo "  ✓ Servicio no estaba ejecutándose"
fi

# Deshabilitar servicio
echo -e "${YELLOW}[2/7]${NC} Deshabilitando servicio..."
if systemctl is-enabled --quiet traefik 2>/dev/null; then
    systemctl disable traefik
    echo "  ✓ Servicio deshabilitado"
else
    echo "  ✓ Servicio no estaba habilitado"
fi

# Eliminar archivo de servicio systemd
echo -e "${YELLOW}[3/7]${NC} Eliminando servicio systemd..."
if [ -f "$TRAEFIK_SERVICE" ]; then
    rm -f $TRAEFIK_SERVICE
    systemctl daemon-reload
    echo "  ✓ Servicio eliminado"
else
    echo "  ✓ Archivo de servicio no encontrado"
fi

# Eliminar binario
echo -e "${YELLOW}[4/7]${NC} Eliminando binario..."
if [ -f "$TRAEFIK_BIN" ]; then
    rm -f $TRAEFIK_BIN
    echo "  ✓ Binario eliminado"
else
    echo "  ✓ Binario no encontrado"
fi

# Eliminar directorios
echo -e "${YELLOW}[5/7]${NC} Eliminando directorios..."

if [ -d "$TRAEFIK_DIR" ]; then
    rm -rf $TRAEFIK_DIR
    echo "  ✓ Directorio $TRAEFIK_DIR eliminado"
fi

if [ -d "$TRAEFIK_CONFIG_DIR" ]; then
    # Hacer backup de la configuración antes de eliminar
    BACKUP_DIR="/tmp/traefik-backup-$(date +%Y%m%d-%H%M%S)"
    mkdir -p $BACKUP_DIR
    cp -r $TRAEFIK_CONFIG_DIR $BACKUP_DIR/
    echo "  ✓ Backup de configuración guardado en: $BACKUP_DIR"
    
    rm -rf $TRAEFIK_CONFIG_DIR
    echo "  ✓ Directorio $TRAEFIK_CONFIG_DIR eliminado"
fi

if [ -d "$TRAEFIK_LOG_DIR" ]; then
    # Hacer backup de los logs antes de eliminar
    if [ ! -d "$BACKUP_DIR" ]; then
        BACKUP_DIR="/tmp/traefik-backup-$(date +%Y%m%d-%H%M%S)"
        mkdir -p $BACKUP_DIR
    fi
    cp -r $TRAEFIK_LOG_DIR $BACKUP_DIR/
    echo "  ✓ Backup de logs guardado en: $BACKUP_DIR"
    
    rm -rf $TRAEFIK_LOG_DIR
    echo "  ✓ Directorio $TRAEFIK_LOG_DIR eliminado"
fi

# Eliminar usuario
echo -e "${YELLOW}[6/7]${NC} Eliminando usuario del sistema..."
if id -u $TRAEFIK_USER > /dev/null 2>&1; then
    userdel $TRAEFIK_USER
    echo "  ✓ Usuario '$TRAEFIK_USER' eliminado"
else
    echo "  ✓ Usuario no encontrado"
fi

# Verificación final
echo -e "${YELLOW}[7/7]${NC} Verificando desinstalación..."
ELEMENTOS_RESTANTES=0

if [ -f "$TRAEFIK_BIN" ]; then
    echo "  ⚠ Binario aún existe: $TRAEFIK_BIN"
    ELEMENTOS_RESTANTES=$((ELEMENTOS_RESTANTES + 1))
fi

if [ -d "$TRAEFIK_CONFIG_DIR" ]; then
    echo "  ⚠ Configuración aún existe: $TRAEFIK_CONFIG_DIR"
    ELEMENTOS_RESTANTES=$((ELEMENTOS_RESTANTES + 1))
fi

if systemctl list-unit-files | grep -q traefik.service; then
    echo "  ⚠ Servicio systemd aún registrado"
    ELEMENTOS_RESTANTES=$((ELEMENTOS_RESTANTES + 1))
fi

if [ $ELEMENTOS_RESTANTES -eq 0 ]; then
    echo "  ✓ Desinstalación completa verificada"
else
    echo "  ⚠ Se encontraron $ELEMENTOS_RESTANTES elementos restantes"
fi

echo ""
if [ -d "$BACKUP_DIR" ]; then
    echo -e "${GREEN}=== Desinstalación completada ===${NC}"
    echo ""
    echo "Traefik ha sido eliminado completamente del sistema."
    echo -e "${YELLOW}Backup guardado en:${NC} $BACKUP_DIR"
    echo ""
    echo "Si deseas eliminar el backup también, ejecuta:"
    echo "  sudo rm -rf $BACKUP_DIR"
else
    echo -e "${GREEN}=== Desinstalación completada ===${NC}"
    echo ""
    echo "Traefik ha sido eliminado completamente del sistema."
fi
echo ""

