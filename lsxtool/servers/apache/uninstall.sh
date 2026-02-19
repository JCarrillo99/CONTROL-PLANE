#!/bin/bash
# Script de desinstalación completa de Apache + Sistema de Sincronización

set -e

# === Variables ===
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE_DIR="$SCRIPT_DIR/configuration"
SYNC_DIR="$SCRIPT_DIR/sync"

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${GREEN}=========================================="
echo "  DESINSTALADOR COMPLETO DE APACHE + SYNC"
echo -e "==========================================${NC}"

# === Verificar permisos root ===
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}❌ Este script debe ejecutarse como root${NC}"
    exit 1
fi

# === Confirmación de desinstalación ===
echo -e "\n${YELLOW}⚠  Esta acción desinstalará completamente:${NC}"
echo "   - Apache y sus dependencias"
echo "   - Sistema de sincronización"
echo "   - Archivos de configuración"
echo "   - Logs del sistema"
echo ""
read -rp "¿Estás seguro de que deseas continuar? (s/n): " CONFIRM

if [[ ! "$CONFIRM" =~ ^[Ss]$ ]]; then
    echo -e "${YELLOW}❌ Desinstalación cancelada${NC}"
    exit 0
fi

# === Paso 1: Detener y desinstalar servicio de sincronización ===
echo -e "\n${BLUE}[1/6]${NC} Desinstalando servicio de sincronización..."
if [ -d "$SYNC_DIR" ] && [ -f "$SYNC_DIR/manage-sync.sh" ]; then
    chmod +x "$SYNC_DIR/manage-sync.sh"
    "$SYNC_DIR/manage-sync.sh" uninstall 2>/dev/null || true
    echo -e "${GREEN}✔ Servicio de sincronización desinstalado${NC}"
else
    echo -e "${YELLOW}⚠ No se encontró el sistema de sincronización${NC}"
fi

# === Paso 2: Detener y deshabilitar Apache ===
echo -e "${BLUE}[2/6]${NC} Deteniendo servicios de Apache..."
systemctl stop apache2 2>/dev/null || true
systemctl disable apache2 2>/dev/null || true
echo -e "${GREEN}✔ Servicios de Apache detenidos${NC}"

# === Paso 3: Desinstalar paquetes ===
echo -e "${BLUE}[3/6]${NC} Desinstalando paquetes..."
{
    apt-get remove --purge -y apache2 apache2-bin apache2-data apache2-utils || true
    apt-get remove --purge -y inotify-tools rsync || true
    apt-get autoremove -y
} 2>/dev/null
echo -e "${GREEN}✔ Paquetes desinstalados${NC}"

# === Paso 4: Limpiar archivos y directorios del sistema ===
echo -e "${BLUE}[4/6]${NC} Limpiando archivos del sistema..."

# Limpiar archivos de configuración del sistema
if [ -d "/etc/apache2" ]; then
    rm -rf /etc/apache2
    echo -e "  🧹 Directorio /etc/apache2 eliminado"
fi

# Limpiar logs de Apache
if [ -d "/var/log/apache2" ]; then
    rm -rf /var/log/apache2
    echo -e "  🧹 Logs de Apache eliminados"
fi

# Limpiar logs de instalación y sincronización
rm -f /var/log/apache-install.log 2>/dev/null || true
rm -f /var/log/apache-sync.log 2>/dev/null || true

# Limpiar archivos temporales y cache
rm -rf /var/cache/apache2 2>/dev/null || true

# === Paso 5: Limpiar enlaces simbólicos viejos ===
echo -e "${BLUE}[5/6]${NC} Limpiando enlaces simbólicos..."

if [ -d "$BASE_DIR" ]; then
    # Eliminar todos los enlaces simbólicos recursivamente
    find "$BASE_DIR" -type l -delete 2>/dev/null || true
    echo -e "${GREEN}✔ Enlaces simbólicos eliminados${NC}"
fi

# === Paso 6: Limpiar archivos locales del proyecto ===
echo -e "${BLUE}[6/6]${NC} Limpiando archivos locales..."

# Preguntar si eliminar configuración local
read -rp "¿Deseas eliminar también los archivos de configuración local? (s/n): " DELETE_LOCAL

if [[ "$DELETE_LOCAL" =~ ^[Ss]$ ]]; then
    if [ -d "$BASE_DIR" ]; then
        rm -rf "$BASE_DIR"
        echo -e "  🧹 Configuración local eliminada: $BASE_DIR"
    fi
    
    # NOTA: NO eliminamos sync/ ni otros scripts porque son parte del proyecto
    echo -e "  📁 Scripts del proyecto conservados (sync/, fix-permissions.sh)"
else
    echo -e "  📁 Archivos locales conservados en: $SCRIPT_DIR"
fi

# === Final ===
echo -e "\n${GREEN}=========================================="
echo "  ✅ DESINSTALACIÓN COMPLETADA"
echo -e "==========================================${NC}"

echo -e "\n${YELLOW}📝 Resumen de la desinstalación:${NC}"
echo "   - Apache y dependencias: ❌ Eliminado"
echo "   - Servicios: ❌ Detenidos y deshabilitados"
echo "   - Archivos del sistema: ❌ Eliminados"
if [[ "$DELETE_LOCAL" =~ ^[Ss]$ ]]; then
    echo "   - Archivos locales: ❌ Eliminados"
else
    echo "   - Archivos locales: ✅ Conservados"
fi

echo -e "\n${BLUE}💡 Recomendación:${NC}"
echo "   Ejecuta 'sudo apt update' para refrescar la lista de paquetes"

