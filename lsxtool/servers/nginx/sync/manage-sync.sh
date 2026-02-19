#!/bin/bash
# =====================================================
# Script: manage-sync.sh
# Autor: LSX
# Propósito: Gestionar el servicio de sincronización de Nginx
# =====================================================

set -Eeuo pipefail
trap 'echo -e "\033[0;31m❌ Error en línea $LINENO (código $?)\033[0m"' ERR

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_FILE="$SCRIPT_DIR/nginx-sync.service"
DAEMON_SCRIPT="$SCRIPT_DIR/nginx-sync-daemon.sh"
SYSTEM_SERVICE_FILE="/etc/systemd/system/nginx-sync.service"
LOG_FILE="/var/log/nginx-sync.log"

# Verificar root
check_root() {
    if [ "$EUID" -ne 0 ]; then
        echo -e "${RED}❌ Este script debe ejecutarse como root${NC}"
        echo -e "${YELLOW}💡 Ejecuta: sudo $0 $1${NC}"
        exit 1
    fi
}

# Verificar dependencias
check_dependencies() {
    local missing=()
    
    command -v inotifywait &>/dev/null || missing+=("inotify-tools")
    command -v rsync &>/dev/null || missing+=("rsync")
    
    if [ ${#missing[@]} -gt 0 ]; then
        echo -e "${RED}❌ Faltan dependencias: ${missing[*]}${NC}"
        echo -e "${YELLOW}💡 Instalando dependencias...${NC}"
        apt-get update -qq
        apt-get install -y "${missing[@]}"
        echo -e "${GREEN}✔ Dependencias instaladas${NC}"
    fi
}

# Instalar el servicio
install_service() {
    echo -e "${BLUE}🔧 Instalando servicio nginx-sync...${NC}"
    
    # Verificar e instalar dependencias
    check_dependencies

    if [ ! -f "$SERVICE_FILE" ]; then
        echo -e "${RED}❌ No se encontró: $SERVICE_FILE${NC}"
        exit 1
    fi
    if [ ! -f "$DAEMON_SCRIPT" ]; then
        echo -e "${RED}❌ No se encontró: $DAEMON_SCRIPT${NC}"
        exit 1
    fi

    chmod +x "$DAEMON_SCRIPT"
    echo -e "${GREEN}✔ Permisos otorgados a daemon${NC}"

    # Actualizar rutas dinámicamente en el archivo de servicio
    echo -e "${BLUE}🔧 Configurando rutas automáticamente...${NC}"
    sed "s|WorkingDirectory=.*|WorkingDirectory=$SCRIPT_DIR|g" "$SERVICE_FILE" | \
    sed "s|ExecStart=.*|ExecStart=$DAEMON_SCRIPT|g" > "$SYSTEM_SERVICE_FILE"
    echo -e "${GREEN}✔ Rutas configuradas: $SCRIPT_DIR${NC}"

    systemctl daemon-reload
    systemctl enable nginx-sync.service
    echo -e "${GREEN}✔ Servicio habilitado para inicio automático${NC}"

    echo -e "\n${GREEN}✅ Servicio instalado correctamente${NC}"
    echo -e "${YELLOW}💡 Para iniciar el servicio ejecuta: sudo $0 start${NC}"
}

# Desinstalar el servicio
uninstall_service() {
    echo -e "${YELLOW}🗑️  Desinstalando servicio nginx-sync...${NC}"

    if systemctl is-active --quiet nginx-sync.service; then
        systemctl stop nginx-sync.service
        echo -e "${GREEN}✔ Servicio detenido${NC}"
    fi

    systemctl disable nginx-sync.service 2>/dev/null || true
    rm -f "$SYSTEM_SERVICE_FILE"
    systemctl daemon-reload

    echo -e "${GREEN}✅ Servicio desinstalado correctamente${NC}"
}

# Control de servicio
start_service() {
    echo -e "${BLUE}▶️  Iniciando servicio nginx-sync...${NC}"
    systemctl start nginx-sync.service || {
        echo -e "${RED}❌ No se pudo iniciar. Verifica con:${NC} systemctl status nginx-sync.service"
        exit 1
    }
    sleep 2
    systemctl is-active --quiet nginx-sync.service &&
        echo -e "${GREEN}✅ Servicio iniciado correctamente${NC}" ||
        echo -e "${RED}❌ Error al iniciar el servicio${NC}"
}

stop_service() { echo -e "${YELLOW}⏹️  Deteniendo...${NC}"; systemctl stop nginx-sync.service; }
restart_service() { echo -e "${BLUE}🔄 Reiniciando...${NC}"; systemctl restart nginx-sync.service; }
status_service() { systemctl status nginx-sync.service; }

logs_service() {
    echo -e "${BLUE}📋 Mostrando logs (Ctrl+C para salir)...${NC}"
    [ -f "$LOG_FILE" ] && tail -f "$LOG_FILE" || echo -e "${YELLOW}⚠ No hay logs aún${NC}"
}

run_manual() { echo -e "${BLUE}🐛 Modo debug activo...${NC}"; "$DAEMON_SCRIPT"; }

show_help() {
    cat << EOF
${BLUE}=== GESTIÓN DE NGINX SYNC DAEMON ===${NC}
Uso: sudo $0 [comando]
Comandos:
  install   Instala el servicio
  uninstall Elimina el servicio
  start     Inicia el daemon
  stop      Detiene el daemon
  restart   Reinicia el daemon
  status    Verifica su estado
  logs      Muestra logs
  manual    Ejecuta modo debug
EOF
}

main() {
    check_root
    case "${1:-help}" in
        install) install_service ;;
        uninstall) uninstall_service ;;
        start) start_service ;;
        stop) stop_service ;;
        restart) restart_service ;;
        status) status_service ;;
        logs) logs_service ;;
        manual) run_manual ;;
        help|--help|-h) show_help ;;
        *) echo -e "${RED}❌ Comando inválido: $1${NC}"; show_help; exit 1 ;;
    esac
}

main "$@"

