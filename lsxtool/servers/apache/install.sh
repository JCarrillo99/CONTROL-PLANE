#!/bin/bash
# =====================================================
# Script: install-apache-sync.sh
# Autor: LSX
# Propósito: Instalación base de Apache + opción de sistema
#           de sincronización automática
# =====================================================

set -e

# ===================== Variables =====================
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE_DIR="$SCRIPT_DIR/configuration"
ETC_DIR="$BASE_DIR/etc/apache2"
VAR_DIR="$BASE_DIR/var/www"
SYNC_DIR="$SCRIPT_DIR/sync"
LOG_INSTALL="/var/log/apache-install.log"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# ===================== Logging =====================
exec > >(tee -a "$LOG_INSTALL") 2>&1

echo -e "${GREEN}=========================================="
echo "  INSTALADOR DE APACHE + SYNC AUTOMÁTICO"
echo -e "==========================================${NC}"

# ===================== Verificación =====================
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}❌ Este script debe ejecutarse como root${NC}"
    exit 1
fi

# ===================== Instalación de Apache =====================
echo -e "\n${BLUE}[1/5]${NC} Verificando e instalando Apache y dependencias..."

# Verificar si apache2 ya está instalado
if systemctl is-active --quiet apache2 2>/dev/null && dpkg -s apache2 >/dev/null 2>&1; then
    echo -e "${GREEN}✔ Apache ya está instalado y ejecutándose${NC}"
else
    apt-get update -qq
    for pkg in apache2 inotify-tools rsync; do
        if dpkg -s $pkg >/dev/null 2>&1; then
            echo -e "${GREEN}✔ $pkg ya instalado${NC}"
        else
            apt-get install -y $pkg
            echo -e "${GREEN}✔ $pkg instalado${NC}"
        fi
    done
fi

# ===================== Estructura de directorios =====================
echo -e "${BLUE}[2/5]${NC} Creando estructura de directorios..."
mkdir -p "$ETC_DIR/sites-available" "$ETC_DIR/sites-enabled" "$ETC_DIR/conf-available" "$ETC_DIR/conf-enabled"
mkdir -p "$ETC_DIR/mods-available" "$ETC_DIR/mods-enabled"
mkdir -p "$VAR_DIR/html"

# Directorios del sistema
for dir in /etc/apache2/sites-available /etc/apache2/sites-enabled /etc/apache2/conf-available /etc/apache2/conf-enabled /etc/apache2/mods-available /etc/apache2/mods-enabled; do
    [[ ! -d "$dir" ]] && mkdir -p "$dir"
done

# Copiar templates si existen
TEMPLATES_DIR="$SCRIPT_DIR/templates"
if [ -d "$TEMPLATES_DIR" ]; then
    # Copiar sites-available de ejemplo
    if [ -d "$TEMPLATES_DIR/sites-available" ]; then
        for site_file in "$TEMPLATES_DIR/sites-available"/*; do
            if [ -f "$site_file" ]; then
                site_name=$(basename "$site_file")
                if [ ! -f "$ETC_DIR/sites-available/$site_name" ]; then
                    cp "$site_file" "$ETC_DIR/sites-available/" 2>/dev/null || true
                    echo -e "${GREEN}✔ Sitio de ejemplo copiado: $site_name${NC}"
                fi
            fi
        done
    fi
    
    # Copiar conf-available de ejemplo
    if [ -d "$TEMPLATES_DIR/conf-available" ]; then
        for conf_file in "$TEMPLATES_DIR/conf-available"/*; do
            if [ -f "$conf_file" ]; then
                conf_name=$(basename "$conf_file")
                if [ ! -f "$ETC_DIR/conf-available/$conf_name" ]; then
                    cp "$conf_file" "$ETC_DIR/conf-available/" 2>/dev/null || true
                    echo -e "${GREEN}✔ Configuración de ejemplo copiada: $conf_name${NC}"
                fi
            fi
        done
    fi
fi

echo -e "${GREEN}✔ Estructura de directorios creada${NC}"

# ===================== Configuración de usuario =====================
echo -e "${BLUE}[3/5]${NC} Configuración de permisos de usuario"
read -rp "¿Deseas configurar permisos de usuario para Apache? (s/n): " CONFIG_USER

if [[ "$CONFIG_USER" =~ ^[Ss]$ ]]; then
    # Crear grupo si no existe
    if ! getent group apache-editors >/dev/null 2>&1; then
        groupadd apache-editors
        echo -e "${GREEN}✔ Grupo 'apache-editors' creado${NC}"
    fi
    
    # Preguntar usuario
    read -rp "Usuario para editar configuraciones de Apache (default: $(who am i | awk '{print $1}' || echo $USER)): " APACHE_USER
    APACHE_USER=${APACHE_USER:-$(who am i | awk '{print $1}' || echo $USER)}
    
    # Agregar usuario al grupo
    if id -u "$APACHE_USER" >/dev/null 2>&1; then
        usermod -a -G apache-editors "$APACHE_USER"
        echo -e "${GREEN}✔ Usuario '$APACHE_USER' agregado al grupo 'apache-editors'${NC}"
        
        # Cambiar ownership del directorio de configuración local
        chown -R "$APACHE_USER:apache-editors" "$ETC_DIR"
        chmod -R g+w "$ETC_DIR"
        echo -e "${GREEN}✔ Permisos de usuario configurados${NC}"
    else
        echo -e "${YELLOW}⚠ Usuario '$APACHE_USER' no encontrado${NC}"
    fi
else
    echo -e "${YELLOW}⚠ Configuración de usuario omitida${NC}"
fi

# ===================== Sistema de sincronización =====================
echo -e "${BLUE}[4/5]${NC} Sistema de sincronización automática"

# Verificar si el servicio ya está instalado
SYNC_INSTALLED=false
if [ -f "/etc/systemd/system/apache-sync.service" ]; then
    SYNC_INSTALLED=true
    echo -e "${GREEN}✔ Servicio apache-sync ya instalado${NC}"
    
    if systemctl is-active --quiet apache-sync.service; then
        echo -e "${GREEN}✔ Servicio apache-sync ejecutándose${NC}"
    else
        read -rp "El servicio está instalado pero no ejecutándose. ¿Iniciarlo? (S/n): " START_SYNC
        START_SYNC=${START_SYNC:-s}
        if [[ "$START_SYNC" =~ ^[Ss]$ ]]; then
            if [ -d "$SYNC_DIR" ] && [ -f "$SYNC_DIR/manage-sync.sh" ]; then
                chmod +x "$SYNC_DIR/manage-sync.sh"
                "$SYNC_DIR/manage-sync.sh" start
            fi
        fi
    fi
else
    # No está instalado, preguntar si instalarlo
    echo -e "${YELLOW}⚠️  IMPORTANTE: inotify NO funciona en /mnt/c/ (limitación de WSL)${NC}"
    echo -e "${YELLOW}   La sincronización inicial funciona, pero cambios en tiempo real NO.${NC}"
    echo -e "${YELLOW}   Alternativa: Usar 'sudo rsync' manualmente después de editar.${NC}"
    echo ""
    read -rp "¿Deseas instalar el sistema de sincronización de todas formas? (S/n): " INSTALL_SYNC
    INSTALL_SYNC=${INSTALL_SYNC:-s}
    
    if [[ "$INSTALL_SYNC" =~ ^[Ss]$ ]]; then
        if [ -d "$SYNC_DIR" ] && [ -f "$SYNC_DIR/manage-sync.sh" ]; then
            chmod +x "$SYNC_DIR/manage-sync.sh"
            chmod +x "$SYNC_DIR/apache-sync-daemon.sh"
            "$SYNC_DIR/manage-sync.sh" install
            "$SYNC_DIR/manage-sync.sh" start
            echo -e "${GREEN}✔ Sistema de sincronización instalado e iniciado${NC}"
            SYNC_INSTALLED=true
        else
            echo -e "${YELLOW}⚠ No se encontró el directorio de sincronización${NC}"
        fi
    else
        echo -e "${YELLOW}⚠ Sincronización omitida${NC}"
    fi
fi

# ===================== Sincronización inicial manual =====================
echo -e "${BLUE}[5/5]${NC} Sincronización inicial de archivos..."

# Detectar si estamos en WSL
IS_WSL=false
if grep -qi microsoft /proc/version 2>/dev/null; then
    IS_WSL=true
    echo -e "${YELLOW}Detectado WSL - usando cp para sincronización${NC}"
fi

# Sincronizar ports.conf primero
if [ -f "$ETC_DIR/ports.conf" ]; then
    if [ "$IS_WSL" = true ]; then
        cp -f "$ETC_DIR/ports.conf" "/etc/apache2/ports.conf" 2>/dev/null || true
    else
        cp -f "$ETC_DIR/ports.conf" "/etc/apache2/ports.conf" 2>/dev/null || true
    fi
    chown root:root "/etc/apache2/ports.conf" 2>/dev/null || true
    chmod 644 "/etc/apache2/ports.conf" 2>/dev/null || true
    echo -e "${GREEN}✔ ports.conf sincronizado (root:root)${NC}"
fi

# Crear symlink para mime.types si no existe
if [ ! -f "/etc/apache2/mime.types" ] && [ -f "/etc/mime.types" ]; then
    ln -sf /etc/mime.types /etc/apache2/mime.types 2>/dev/null || true
    echo -e "${GREEN}✔ Symlink mime.types creado${NC}"
fi

# Sincronizar sites-available
if [ -d "$ETC_DIR/sites-available" ] && [ "$(ls -A $ETC_DIR/sites-available 2>/dev/null)" ]; then
    if [ "$IS_WSL" = true ]; then
        cp -rf "$ETC_DIR/sites-available"/* "/etc/apache2/sites-available/" 2>/dev/null || true
    else
        rsync -av "$ETC_DIR/sites-available/" "/etc/apache2/sites-available/" >/dev/null 2>&1
    fi
    find "/etc/apache2/sites-available" -type f -exec chown root:root {} \; 2>/dev/null
    find "/etc/apache2/sites-available" -type f -exec chmod 644 {} \; 2>/dev/null
    echo -e "${GREEN}✔ Sites-available sincronizados (root:root)${NC}"
fi

# Sincronizar sites-enabled
if [ -d "$ETC_DIR/sites-enabled" ] && [ "$(ls -A $ETC_DIR/sites-enabled 2>/dev/null)" ]; then
    if [ "$IS_WSL" = true ]; then
        cp -rf "$ETC_DIR/sites-enabled"/* "/etc/apache2/sites-enabled/" 2>/dev/null || true
    else
        rsync -av "$ETC_DIR/sites-enabled/" "/etc/apache2/sites-enabled/" >/dev/null 2>&1
    fi
    find "/etc/apache2/sites-enabled" -type f -exec chown root:root {} \; 2>/dev/null
    find "/etc/apache2/sites-enabled" -type f -exec chmod 644 {} \; 2>/dev/null
    echo -e "${GREEN}✔ Sites-enabled sincronizados (root:root)${NC}"
fi

# Sincronizar conf-available
if [ -d "$ETC_DIR/conf-available" ] && [ "$(ls -A $ETC_DIR/conf-available 2>/dev/null)" ]; then
    if [ "$IS_WSL" = true ]; then
        cp -rf "$ETC_DIR/conf-available"/* "/etc/apache2/conf-available/" 2>/dev/null || true
    else
        rsync -av "$ETC_DIR/conf-available/" "/etc/apache2/conf-available/" >/dev/null 2>&1
    fi
    find "/etc/apache2/conf-available" -type f -exec chown root:root {} \; 2>/dev/null
    find "/etc/apache2/conf-available" -type f -exec chmod 644 {} \; 2>/dev/null
    echo -e "${GREEN}✔ Conf-available sincronizados (root:root)${NC}"
fi

# Sincronizar conf-enabled
if [ -d "$ETC_DIR/conf-enabled" ] && [ "$(ls -A $ETC_DIR/conf-enabled 2>/dev/null)" ]; then
    if [ "$IS_WSL" = true ]; then
        cp -rf "$ETC_DIR/conf-enabled"/* "/etc/apache2/conf-enabled/" 2>/dev/null || true
    else
        rsync -av "$ETC_DIR/conf-enabled/" "/etc/apache2/conf-enabled/" >/dev/null 2>&1
    fi
    find "/etc/apache2/conf-enabled" -type f -exec chown root:root {} \; 2>/dev/null
    find "/etc/apache2/conf-enabled" -type f -exec chmod 644 {} \; 2>/dev/null
    echo -e "${GREEN}✔ Conf-enabled sincronizados (root:root)${NC}"
fi

# Sincronizar mods-available
if [ -d "$ETC_DIR/mods-available" ] && [ "$(ls -A $ETC_DIR/mods-available 2>/dev/null)" ]; then
    if [ "$IS_WSL" = true ]; then
        cp -rf "$ETC_DIR/mods-available"/* "/etc/apache2/mods-available/" 2>/dev/null || true
    else
        rsync -av "$ETC_DIR/mods-available/" "/etc/apache2/mods-available/" >/dev/null 2>&1
    fi
    find "/etc/apache2/mods-available" -type f -exec chown root:root {} \; 2>/dev/null
    find "/etc/apache2/mods-available" -type f -exec chmod 644 {} \; 2>/dev/null
    echo -e "${GREEN}✔ Mods-available sincronizados (root:root)${NC}"
fi

# Sincronizar mods-enabled
if [ -d "$ETC_DIR/mods-enabled" ] && [ "$(ls -A $ETC_DIR/mods-enabled 2>/dev/null)" ]; then
    if [ "$IS_WSL" = true ]; then
        cp -rf "$ETC_DIR/mods-enabled"/* "/etc/apache2/mods-enabled/" 2>/dev/null || true
    else
        rsync -av "$ETC_DIR/mods-enabled/" "/etc/apache2/mods-enabled/" >/dev/null 2>&1
    fi
    find "/etc/apache2/mods-enabled" -type f -exec chown root:root {} \; 2>/dev/null
    find "/etc/apache2/mods-enabled" -type f -exec chmod 644 {} \; 2>/dev/null
    echo -e "${GREEN}✔ Mods-enabled sincronizados (root:root)${NC}"
fi

# ===================== Iniciar Apache =====================
echo -e "\n${BLUE}Iniciando Apache...${NC}"
if apache2ctl configtest >/dev/null 2>&1; then
    systemctl restart apache2
    systemctl enable apache2
    echo -e "${GREEN}✓ Apache instalado y ejecutándose${NC}"
else
    echo -e "${YELLOW}⚠ Configuración de Apache incorrecta. No se reinició${NC}"
fi

# ===================== Resumen =====================
echo -e "\n${GREEN}=========================================="
echo "  ✅ INSTALACIÓN COMPLETADA"
echo -e "==========================================${NC}"

echo -e "${BLUE}📁 Estructura creada:${NC}"
echo "   $BASE_DIR"

echo -e "\n${BLUE}🔧 Pasos siguientes:${NC}"

if [ "$SYNC_INSTALLED" = true ]; then
    echo -e "${YELLOW}1. Verificar sincronización:${NC}"
    echo "   cd $SYNC_DIR"
    echo "   sudo ./manage-sync.sh status"
    echo "   sudo ./manage-sync.sh logs"
fi

echo -e "\n${BLUE}📝 Uso diario:${NC}"
echo "   - Edita archivos en: $ETC_DIR/sites-available/"
echo "   - Habilitar sitio: a2ensite nombre-sitio"
echo "   - Deshabilitar sitio: a2dissite nombre-sitio"
if [ "$SYNC_INSTALLED" = true ]; then
    echo "   - Sincronización automática limitada en /mnt/c/"
fi
echo "   - Probar config: sudo apache2ctl configtest"
echo "   - Recargar manual: sudo systemctl reload apache2"
echo ""
if grep -qi microsoft /proc/version 2>/dev/null; then
    echo -e "${BLUE}🔄 Sincronización manual (recomendado en WSL):${NC}"
    echo "   sudo cp -rf $ETC_DIR/sites-available/* /etc/apache2/sites-available/"
    echo "   sudo cp -rf $ETC_DIR/mods-available/* /etc/apache2/mods-available/"
    echo "   sudo find /etc/apache2/sites-available -exec chown root:root {} \\;"
    echo "   sudo find /etc/apache2/mods-available -exec chown root:root {} \\;"
    echo "   sudo apache2ctl configtest && sudo systemctl reload apache2"
else
    echo -e "${BLUE}🔄 Sincronización manual:${NC}"
    echo "   sudo rsync -av $ETC_DIR/sites-available/ /etc/apache2/sites-available/"
    echo "   sudo rsync -av $ETC_DIR/mods-available/ /etc/apache2/mods-available/"
    echo "   sudo systemctl reload apache2"
fi

