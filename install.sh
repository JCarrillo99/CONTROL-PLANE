#!/bin/bash
# Instalador del módulo Servers
# Verifica dependencias y prepara el entorno

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${GREEN}=========================================="
echo "  INSTALADOR DEL MÓDULO SERVERS"
echo -e "==========================================${NC}"
echo ""

# Función para verificar si un comando existe
command_exists() {
    command -v "$1" &> /dev/null
}

# Función para verificar una dependencia
check_dependency() {
    local cmd="$1"
    local name="$2"
    local install_cmd="$3"
    
    if command_exists "$cmd"; then
        echo -e "${GREEN}✔${NC} $name está instalado"
        return 0
    else
        echo -e "${YELLOW}⚠${NC} $name NO está instalado"
        
        if [ -n "$install_cmd" ] && [ "$EUID" -eq 0 ]; then
            echo -e "  ${BLUE}→${NC} Instalando $name..."
            eval "$install_cmd"
            
            if command_exists "$cmd"; then
                echo -e "  ${GREEN}✔${NC} $name instalado correctamente"
                return 0
            else
                echo -e "  ${RED}✗${NC} Error al instalar $name"
                return 1
            fi
        else
            echo -e "  ${YELLOW}→${NC} Instala manualmente: $install_cmd"
            return 1
        fi
    fi
}

# Paso 1: Verificar dependencias del sistema
echo -e "${CYAN}[1/4]${NC} Verificando dependencias del sistema..."
echo ""

missing_deps=0

# Verificar bash (mínimo 4.0)
if command_exists bash; then
    bash_version=$(bash --version | head -n1 | grep -oP '\d+\.\d+' | head -n1)
    major_version=$(echo "$bash_version" | cut -d. -f1)
    
    if [ "$major_version" -ge 4 ]; then
        echo -e "${GREEN}✔${NC} Bash $bash_version (OK)"
    else
        echo -e "${RED}✗${NC} Bash $bash_version (requiere 4.0+)"
        missing_deps=1
    fi
else
    echo -e "${RED}✗${NC} Bash no está instalado"
    missing_deps=1
fi

# Verificar jq
check_dependency "jq" "jq (procesador JSON)" "apt-get update && apt-get install -y jq" || missing_deps=1

# Verificar systemctl
check_dependency "systemctl" "systemd" "" || {
    echo -e "${RED}  Este sistema no usa systemd. Algunos submódulos pueden no funcionar.${NC}"
}

# Verificar curl o wget
if command_exists curl; then
    echo -e "${GREEN}✔${NC} curl está instalado"
elif command_exists wget; then
    echo -e "${GREEN}✔${NC} wget está instalado"
else
    echo -e "${YELLOW}⚠${NC} Ni curl ni wget están instalados"
    check_dependency "curl" "curl" "apt-get update && apt-get install -y curl" || missing_deps=1
fi

echo ""

if [ $missing_deps -eq 1 ]; then
    echo -e "${RED}=========================================="
    echo "  ⚠️  DEPENDENCIAS FALTANTES"
    echo -e "==========================================${NC}"
    echo ""
    echo "Instala las dependencias faltantes antes de continuar."
    echo ""
    echo "En Debian/Ubuntu:"
    echo "  sudo apt-get update"
    echo "  sudo apt-get install -y jq curl"
    echo ""
    exit 1
fi

echo -e "${GREEN}✔ Todas las dependencias están instaladas${NC}"
echo ""

# Paso 2: Verificar permisos
echo -e "${CYAN}[2/4]${NC} Verificando permisos..."
echo ""

if [ "$EUID" -eq 0 ]; then
    echo -e "${GREEN}✔${NC} Ejecutando como root"
    echo -e "  ${BLUE}→${NC} Podrás instalar submódulos que requieren permisos elevados"
else
    echo -e "${YELLOW}⚠${NC} Ejecutando como usuario regular"
    echo -e "  ${BLUE}→${NC} Algunos comandos (install/uninstall) requerirán sudo"
    echo -e "  ${BLUE}→${NC} Los comandos de consulta (list/status) funcionarán normalmente"
fi
echo ""

# Paso 3: Verificar estructura del módulo
echo -e "${CYAN}[3/4]${NC} Verificando estructura del módulo..."
echo ""

files_ok=true

# Verificar archivos obligatorios
if [ -f "$SCRIPT_DIR/module.json" ]; then
    echo -e "${GREEN}✔${NC} module.json encontrado"
    
    # Validar JSON
    if jq empty "$SCRIPT_DIR/module.json" 2>/dev/null; then
        echo -e "  ${GREEN}→${NC} JSON válido"
        
        # Leer metadata
        module_name=$(jq -r '.name // "N/A"' "$SCRIPT_DIR/module.json")
        module_version=$(jq -r '.version // "N/A"' "$SCRIPT_DIR/module.json")
        module_alias=$(jq -r '.alias // "N/A"' "$SCRIPT_DIR/module.json")
        
        echo -e "  ${BLUE}→${NC} Nombre: $module_name"
        echo -e "  ${BLUE}→${NC} Versión: $module_version"
        echo -e "  ${BLUE}→${NC} Alias: $module_alias"
    else
        echo -e "  ${RED}✗${NC} JSON inválido"
        files_ok=false
    fi
else
    echo -e "${RED}✗${NC} module.json NO encontrado"
    files_ok=false
fi

if [ -f "$SCRIPT_DIR/cli.sh" ]; then
    echo -e "${GREEN}✔${NC} cli.sh encontrado"
    
    if [ -x "$SCRIPT_DIR/cli.sh" ]; then
        echo -e "  ${GREEN}→${NC} Tiene permisos de ejecución"
    else
        echo -e "  ${YELLOW}→${NC} Agregando permisos de ejecución"
        chmod +x "$SCRIPT_DIR/cli.sh"
    fi
else
    echo -e "${RED}✗${NC} cli.sh NO encontrado"
    files_ok=false
fi

# Verificar submódulos
if [ -f "$SCRIPT_DIR/module.json" ]; then
    submodule_count=$(jq '.submodules | length' "$SCRIPT_DIR/module.json" 2>/dev/null || echo "0")
    echo -e "${BLUE}→${NC} Submódulos detectados: $submodule_count"
    
    if [ "$submodule_count" -gt 0 ]; then
        jq -r '.submodules[] | "  - \(.id): \(.name)"' "$SCRIPT_DIR/module.json" 2>/dev/null
    fi
fi

echo ""

if [ "$files_ok" = false ]; then
    echo -e "${RED}=========================================="
    echo "  ⚠️  ESTRUCTURA INCOMPLETA"
    echo -e "==========================================${NC}"
    echo ""
    echo "El módulo no tiene todos los archivos necesarios."
    exit 1
fi

echo -e "${GREEN}✔ Estructura del módulo correcta${NC}"
echo ""

# Paso 4: Finalizar
echo -e "${CYAN}[4/4]${NC} Finalizando instalación..."
echo ""

# Hacer ejecutables todos los scripts de instalación/desinstalación
if [ -d "$SCRIPT_DIR" ]; then
    find "$SCRIPT_DIR" -type f -name "install.sh" -exec chmod +x {} \;
    find "$SCRIPT_DIR" -type f -name "uninstall.sh" -exec chmod +x {} \;
    echo -e "${GREEN}✔${NC} Scripts de submódulos configurados"
fi

echo ""
echo -e "${GREEN}=========================================="
echo "  ✅ INSTALACIÓN COMPLETADA"
echo -e "==========================================${NC}"
echo ""
echo -e "${CYAN}El módulo Servers está listo para usar${NC}"
echo ""
echo "Para ver los comandos disponibles:"
echo -e "  ${YELLOW}lsx $module_alias help${NC}"
echo ""
echo "Para listar submódulos disponibles:"
echo -e "  ${YELLOW}lsx $module_alias list${NC}"
echo ""
echo "Para instalar un submódulo (requiere sudo):"
echo -e "  ${YELLOW}sudo lsx $module_alias install nginx${NC}"
echo -e "  ${YELLOW}sudo lsx $module_alias install traefik${NC}"
echo ""
echo -e "${BLUE}Documentación completa: README.md${NC}"
echo ""

