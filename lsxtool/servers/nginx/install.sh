#!/bin/bash
# =====================================================
# Script: install-nginx-sync.sh
# Autor: LSX
# Propósito: Instalación base de Nginx + opción de sistema
#           de sincronización automática
# =====================================================

set -e

# ===================== Variables =====================
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE_DIR="$SCRIPT_DIR/configuration"
ETC_DIR="$BASE_DIR/etc/nginx"
VAR_DIR="$BASE_DIR/var/www"
SYNC_DIR="$SCRIPT_DIR/sync"
LOG_INSTALL="/var/log/nginx-install.log"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# ===================== Logging =====================
exec > >(tee -a "$LOG_INSTALL") 2>&1

echo -e "${GREEN}=========================================="
echo "  INSTALADOR DE NGINX + SYNC AUTOMÁTICO"
echo -e "==========================================${NC}"

# ===================== Verificación =====================
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}❌ Este script debe ejecutarse como root${NC}"
    exit 1
fi

# ===================== Instalación de Nginx =====================
echo -e "\n${BLUE}[1/5]${NC} Verificando e instalando Nginx y dependencias..."

# Verificar si nginx ya está instalado
if systemctl is-active --quiet nginx 2>/dev/null && dpkg -s nginx >/dev/null 2>&1; then
    echo -e "${GREEN}✔ Nginx ya está instalado y ejecutándose${NC}"
else
    apt-get update -qq
    for pkg in nginx inotify-tools rsync; do
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
mkdir -p "$ETC_DIR/conf.d" "$ETC_DIR/sites-available" "$ETC_DIR/sites-enabled" "$ETC_DIR/snippets"
mkdir -p "$VAR_DIR/html"

# Directorios del sistema
for dir in /etc/nginx/conf.d /etc/nginx/sites-available /etc/nginx/sites-enabled /etc/nginx/snippets; do
    [[ ! -d "$dir" ]] && mkdir -p "$dir"
done

# Copiar templates si existen
TEMPLATES_DIR="$SCRIPT_DIR/templates"
if [ -d "$TEMPLATES_DIR" ]; then
    # Copiar snippets de templates a configuration (solo si no existen)
    if [ -d "$TEMPLATES_DIR/snippets" ]; then
        for snippet_dir in "$TEMPLATES_DIR/snippets"/*; do
            if [ -d "$snippet_dir" ]; then
                snippet_name=$(basename "$snippet_dir")
                if [ ! -d "$ETC_DIR/snippets/$snippet_name" ]; then
                    cp -r "$snippet_dir" "$ETC_DIR/snippets/" 2>/dev/null || true
                    echo -e "${GREEN}✔ Snippet copiado: $snippet_name${NC}"
                fi
            fi
        done
    fi
    
    # Copiar conf.d de ejemplo (solo si no existen)
    if [ -d "$TEMPLATES_DIR/conf.d" ]; then
        for site_dir in "$TEMPLATES_DIR/conf.d"/*; do
            if [ -d "$site_dir" ]; then
                site_name=$(basename "$site_dir")
                if [ ! -d "$ETC_DIR/conf.d/$site_name" ]; then
                    cp -r "$site_dir" "$ETC_DIR/conf.d/" 2>/dev/null || true
                    echo -e "${GREEN}✔ Sitio de ejemplo copiado: $site_name${NC}"
                fi
            fi
        done
    fi
    
    # Copiar ejemplos de configuración .conf si existen
    for conf_file in "$TEMPLATES_DIR"/*.conf; do
        if [ -f "$conf_file" ]; then
            conf_name=$(basename "$conf_file")
            if [ ! -f "$ETC_DIR/sites-available/$conf_name" ]; then
                cp "$conf_file" "$ETC_DIR/sites-available/" 2>/dev/null || true
            fi
        fi
    done
fi

echo -e "${GREEN}✔ Estructura de directorios creada${NC}"

# ===================== Configuración de usuario =====================
echo -e "${BLUE}[3/5]${NC} Configuración de permisos de usuario"
read -rp "¿Deseas configurar permisos de usuario para Nginx? (s/n): " CONFIG_USER

if [[ "$CONFIG_USER" =~ ^[Ss]$ ]]; then
    if [ -f "$SCRIPT_DIR/set-nginx-editor.sh" ]; then
        chmod +x "$SCRIPT_DIR/set-nginx-editor.sh"
        "$SCRIPT_DIR/set-nginx-editor.sh"
        echo -e "${GREEN}✔ Permisos de usuario configurados${NC}"
    else
        echo -e "${YELLOW}⚠ No se encontró set-nginx-editor.sh${NC}"
    fi
else
    echo -e "${YELLOW}⚠ Configuración de usuario omitida${NC}"
fi

# ===================== Sistema de sincronización =====================
echo -e "${BLUE}[4/5]${NC} Sistema de sincronización automática"

# Verificar si el servicio ya está instalado
SYNC_INSTALLED=false
if [ -f "/etc/systemd/system/nginx-sync.service" ]; then
    SYNC_INSTALLED=true
    echo -e "${GREEN}✔ Servicio nginx-sync ya instalado${NC}"
    
    if systemctl is-active --quiet nginx-sync.service; then
        echo -e "${GREEN}✔ Servicio nginx-sync ejecutándose${NC}"
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
            chmod +x "$SYNC_DIR/nginx-sync-daemon.sh"
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

# Sincronizar snippets
if [ -d "$ETC_DIR/snippets" ] && [ "$(ls -A $ETC_DIR/snippets)" ]; then
    if [ "$IS_WSL" = true ]; then
        cp -rf "$ETC_DIR/snippets"/* "/etc/nginx/snippets/" 2>/dev/null || true
    else
        rsync -av "$ETC_DIR/snippets/" "/etc/nginx/snippets/" >/dev/null 2>&1
    fi
    # Ajustar permisos a root:root (seguridad)
    find "/etc/nginx/snippets" -type f -exec chown root:root {} \; 2>/dev/null
    find "/etc/nginx/snippets" -type d -exec chown root:root {} \; 2>/dev/null
    find "/etc/nginx/snippets" -type f -exec chmod 644 {} \; 2>/dev/null
    echo -e "${GREEN}✔ Snippets sincronizados (root:root)${NC}"
fi

# Sincronizar conf.d si hay archivos
if [ -d "$ETC_DIR/conf.d" ] && [ "$(ls -A $ETC_DIR/conf.d)" ]; then
    if [ "$IS_WSL" = true ]; then
        cp -rf "$ETC_DIR/conf.d"/* "/etc/nginx/conf.d/" 2>/dev/null || true
    else
        rsync -av "$ETC_DIR/conf.d/" "/etc/nginx/conf.d/" >/dev/null 2>&1
    fi
    # Ajustar permisos a root:root (seguridad)
    find "/etc/nginx/conf.d" -type f -exec chown root:root {} \; 2>/dev/null
    find "/etc/nginx/conf.d" -type d -exec chown root:root {} \; 2>/dev/null
    find "/etc/nginx/conf.d" -type f -exec chmod 644 {} \; 2>/dev/null
    echo -e "${GREEN}✔ Configuraciones sincronizadas (root:root)${NC}"
fi

# ===================== Iniciar Nginx =====================
echo -e "\n${BLUE}Iniciando Nginx...${NC}"
if nginx -t >/dev/null 2>&1; then
    systemctl restart nginx
    systemctl enable nginx
    echo -e "${GREEN}✓ Nginx instalado y ejecutándose${NC}"
else
    echo -e "${YELLOW}⚠ Configuración de Nginx incorrecta. No se reinició${NC}"
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
echo "   - Edita archivos en: $ETC_DIR/conf.d/"
if [ "$SYNC_INSTALLED" = true ]; then
    echo "   - Sincronización automática limitada en /mnt/c/"
fi
echo "   - Probar config: sudo nginx -t"
echo "   - Recargar manual: sudo nginx -s reload"
echo ""
if grep -qi microsoft /proc/version 2>/dev/null; then
    echo -e "${BLUE}🔄 Sincronización manual (recomendado en WSL):${NC}"
    echo "   sudo cp -rf $ETC_DIR/conf.d/* /etc/nginx/conf.d/"
    echo "   sudo find /etc/nginx/conf.d -exec chown root:root {} \\;"
    echo "   sudo nginx -t && sudo nginx -s reload"
else
    echo -e "${BLUE}🔄 Sincronización manual:${NC}"
    echo "   sudo rsync -av $ETC_DIR/conf.d/ /etc/nginx/conf.d/"
    echo "   sudo nginx -s reload"
fi