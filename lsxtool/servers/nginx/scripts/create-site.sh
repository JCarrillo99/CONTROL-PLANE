#!/bin/bash
# =====================================================
# Script: create-site.sh
# Autor: LSX
# Propósito: Crear un nuevo sitio nginx con preset
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
PROJECTS_CONF="$NGINX_DIR/configuration/projects.conf"

# Cargar metadata de proyectos
declare -A PROJECT_DOMAINS
if [ -f "$PROJECTS_CONF" ]; then
    while IFS='|' read -r proj domain; do
        [[ "$proj" =~ ^#.*$ ]] && continue  # Ignorar comentarios
        [ -z "$proj" ] && continue
        PROJECT_DOMAINS["$proj"]="$domain"
    done < "$PROJECTS_CONF"
fi

echo -e "${GREEN}=========================================="
echo "  CREAR NUEVO SITIO NGINX"
echo -e "==========================================${NC}\n"

# Verificar root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}❌ Este script debe ejecutarse como root${NC}"
    exit 1
fi

# ==================== PASO 1: Proyecto Principal (Provider) ====================
echo -e "${BLUE}📁 Proyecto principal / Provider:${NC}\n"
echo "  El proyecto es el 'contenedor' principal (ej: lunarsystemx, mi-empresa)"
echo "  Debajo de este irán los subdominios/apps organizados por ambiente"
echo ""
echo "Proyectos existentes:"

# Crear array de proyectos existentes
mapfile -t EXISTING_PROJECTS < <(ls -1 "$CONF_DIR" | grep -v "\.conf$")

if [ ${#EXISTING_PROJECTS[@]} -gt 0 ]; then
    for i in "${!EXISTING_PROJECTS[@]}"; do
        proj="${EXISTING_PROJECTS[$i]}"
        domain="${PROJECT_DOMAINS[$proj]:-N/A}"
        echo "  $((i+1))) $proj → $domain"
    done
    echo ""
    read -rp "Selecciona número o escribe nombre nuevo: " PROJECT_INPUT
    
    # Si es un número, validar y seleccionar
    if [[ "$PROJECT_INPUT" =~ ^[0-9]+$ ]]; then
        if [ "$PROJECT_INPUT" -ge 1 ] && [ "$PROJECT_INPUT" -le "${#EXISTING_PROJECTS[@]}" ]; then
            PROJECT="${EXISTING_PROJECTS[$((PROJECT_INPUT-1))]}"
            BASE_DOMAIN="${PROJECT_DOMAINS[$PROJECT]}"
            echo -e "${GREEN}✔ Seleccionado: $PROJECT ($BASE_DOMAIN)${NC}"
        else
            echo -e "${RED}❌ Opción $PROJECT_INPUT no existe. Opciones válidas: 1-${#EXISTING_PROJECTS[@]}${NC}"
            exit 1
        fi
    else
        # Nombre nuevo
        PROJECT="$PROJECT_INPUT"
        read -rp "Dominio base para $PROJECT (ej: $PROJECT.com): " BASE_DOMAIN
        BASE_DOMAIN=${BASE_DOMAIN:-$PROJECT.com}
        
        # Guardar en projects.conf
        echo "$PROJECT|$BASE_DOMAIN" >> "$PROJECTS_CONF"
        PROJECT_DOMAINS["$PROJECT"]="$BASE_DOMAIN"
        echo -e "${GREEN}✔ Proyecto registrado: $PROJECT → $BASE_DOMAIN${NC}"
    fi
else
    echo "  (No hay proyectos aún)"
    echo ""
    read -rp "Nombre del nuevo proyecto: " PROJECT
    read -rp "Dominio base (ej: $PROJECT.com): " BASE_DOMAIN
    BASE_DOMAIN=${BASE_DOMAIN:-$PROJECT.com}
    
    # Crear projects.conf si no existe
    [ ! -f "$PROJECTS_CONF" ] && echo "# Proyectos: NOMBRE|DOMINIO_BASE" > "$PROJECTS_CONF"
    echo "$PROJECT|$BASE_DOMAIN" >> "$PROJECTS_CONF"
    PROJECT_DOMAINS["$PROJECT"]="$BASE_DOMAIN"
fi

if [ -z "$PROJECT" ]; then
    echo -e "${RED}❌ El proyecto es obligatorio${NC}"
    exit 1
fi

PROJECT_DIR="$CONF_DIR/$PROJECT"
mkdir -p "$PROJECT_DIR"

# ==================== PASO 2: Ambiente ====================
echo -e "\n${BLUE}🌍 Ambiente:${NC}\n"
echo "  1) dev       - Desarrollo"
echo "  2) qa        - Quality Assurance / Staging"
echo "  3) prod      - Producción"
echo ""
read -rp "Selecciona ambiente (1/2/3): " ENV_OPTION

if [[ ! "$ENV_OPTION" =~ ^[1-3]$ ]]; then
    echo -e "${RED}❌ Opción inválida '$ENV_OPTION'. Opciones válidas: 1, 2, 3${NC}"
    exit 1
fi

case "$ENV_OPTION" in
    1) ENVIRONMENT="dev" ;;
    2) ENVIRONMENT="qa" ;;
    3) ENVIRONMENT="prod" ;;
esac

echo -e "${GREEN}✔ Ambiente: $ENVIRONMENT${NC}"

# Crear carpeta de ambiente
ENV_DIR="$PROJECT_DIR/$ENVIRONMENT"
mkdir -p "$ENV_DIR"

# ==================== PASO 3: Subdominio/App ====================
echo -e "\n${BLUE}📱 Nombre de la aplicación/subdominio:${NC}\n"
echo "  Ejemplos: www, api, admin, react-app, my-app"
echo ""
read -rp "Nombre del subdominio/app: " SUBDOM_NAME

if [ -z "$SUBDOM_NAME" ]; then
    echo -e "${RED}❌ El nombre es obligatorio${NC}"
    exit 1
fi

# Crear carpeta para el subdominio
SUBDOM_DIR="$ENV_DIR/$SUBDOM_NAME"
mkdir -p "$SUBDOM_DIR"

# ==================== PASO 4: Dominio ====================
echo -e "\n${BLUE}🌐 Dominio completo:${NC}\n"

# Sugerir dominio basado en ambiente, subdominio y dominio base del proyecto
if [ "$ENVIRONMENT" = "prod" ]; then
    if [ "$SUBDOM_NAME" = "www" ]; then
        SUGGESTED_DOMAIN="$BASE_DOMAIN"
    else
        SUGGESTED_DOMAIN="$SUBDOM_NAME.$BASE_DOMAIN"
    fi
else
    SUGGESTED_DOMAIN="$ENVIRONMENT-$SUBDOM_NAME.$BASE_DOMAIN"
fi

read -rp "Dominio completo (sugerido: $SUGGESTED_DOMAIN): " DOMAIN
DOMAIN=${DOMAIN:-$SUGGESTED_DOMAIN}
echo -e "${GREEN}✔ Dominio: $DOMAIN${NC}"

# ==================== VALIDACIONES ====================
echo -e "\n${BLUE}🔍 Validando configuración...${NC}"

# Verificar si ya existe archivo con ese nombre
CONF_NAME="$(echo $SUBDOM_NAME | tr '[:upper:]' '[:lower:]').conf"
OUTPUT_FILE="$SUBDOM_DIR/$CONF_NAME"

if [ -f "$OUTPUT_FILE" ]; then
    echo -e "${YELLOW}⚠ Ya existe: $OUTPUT_FILE${NC}"
    echo "  1) Sobrescribir"
    echo "  2) Crear backup y sobrescribir"
    echo "  3) Cancelar"
    read -rp "Selecciona opción (1/2/3): " CONFLICT_OPTION
    
    case "$CONFLICT_OPTION" in
        1) rm -f "$OUTPUT_FILE" ;;
        2) mv "$OUTPUT_FILE" "${OUTPUT_FILE}.bak.$(date +%Y%m%d%H%M%S)"
           echo -e "${GREEN}✔ Backup creado${NC}" ;;
        3) echo -e "${YELLOW}Cancelado${NC}"; exit 0 ;;
        *) echo -e "${RED}❌ Opción inválida${NC}"; exit 1 ;;
    esac
fi

# Verificar conflictos de server_name
echo -e "${BLUE}Verificando conflictos de server_name...${NC}"
CONFLICTS=$(find "$CONF_DIR" -type f -name "*.conf" -exec grep -l "server_name.*$DOMAIN" {} \; 2>/dev/null || true)

if [ -n "$CONFLICTS" ]; then
    echo -e "${YELLOW}⚠ El dominio '$DOMAIN' ya está en uso en:${NC}"
    echo "$CONFLICTS" | nl
    read -rp "¿Continuar de todas formas? (s/n): " CONTINUE
    if [[ ! "$CONTINUE" =~ ^[Ss]$ ]]; then
        exit 0
    fi
fi

echo -e "${GREEN}✔ Validaciones completadas${NC}"

# ==================== PASO 4: Tecnología ====================
echo -e "\n${BLUE}💻 Tipo de proyecto:${NC}\n"
echo "  BASE:"
echo "    1) HTML estático"
echo ""
echo "  NODE.JS:"
echo "    2) React SPA"
echo "    3) Vue SPA"
echo "    4) Angular SPA"
echo ""
echo "  PHP:"
echo "    5) PHP (FastCGI)"
echo "    6) Laravel"
echo "    7) Phalcon"
echo ""
read -rp "Selecciona tipo (1-7): " TECH_OPTION

if [[ ! "$TECH_OPTION" =~ ^[1-7]$ ]]; then
    echo -e "${RED}❌ Opción inválida '$TECH_OPTION'. Opciones válidas: 1-7${NC}"
    exit 1
fi

case "$TECH_OPTION" in
    1) TECH="html"; IS_SPA=false; IS_DEV_PROXY=false ;;
    2) TECH="react"; IS_SPA=true; IS_DEV_PROXY=true ;;
    3) TECH="vue"; IS_SPA=true; IS_DEV_PROXY=true ;;
    4) TECH="angular"; IS_SPA=true; IS_DEV_PROXY=true ;;
    5) TECH="php"; IS_SPA=false; IS_DEV_PROXY=false ;;
    6) TECH="laravel"; IS_SPA=false; IS_DEV_PROXY=false ;;
    7) TECH="phalcon"; IS_SPA=false; IS_DEV_PROXY=false ;;
esac

# Seleccionar preset correcto según ambiente
if [ "$IS_DEV_PROXY" = true ] && [ "$ENVIRONMENT" = "dev" ]; then
    # En dev, SPAs usan proxy a servidor de desarrollo
    PRESET="node/${TECH}-spa-dev.conf.template"
    USE_PROXY=true
elif [ "$IS_SPA" = true ]; then
    # En prod/qa, SPAs sirven archivos estáticos
    PRESET="node/${TECH}-spa-prod.conf.template"
    USE_PROXY=false
else
    # Otros presets
    case "$TECH" in
        html) PRESET="base/html-static.conf.template" ;;
        php) PRESET="php/php-fastcgi.conf.template" ;;
        laravel) PRESET="php/laravel.conf.template" ;;
        phalcon) PRESET="php/phalcon.conf.template" ;;
    esac
    USE_PROXY=false
fi

echo -e "${GREEN}✔ Tecnología: $TECH${NC}"
[ "$USE_PROXY" = true ] && echo -e "${YELLOW}  Modo: Proxy a servidor de desarrollo${NC}"

PRESET_FILE="$PRESETS_DIR/$PRESET"
if [ ! -f "$PRESET_FILE" ]; then
    echo -e "${RED}❌ Preset no encontrado: $PRESET_FILE${NC}"
    exit 1
fi

# ==================== PASO 6: Configuración ====================
echo -e "\n${BLUE}⚙️  Configuración:${NC}\n"

# Si es modo proxy (dev con SPA)
if [ "$USE_PROXY" = true ]; then
    echo -e "${YELLOW}Modo desarrollo - Nginx hará proxy al servidor de desarrollo${NC}\n"
    
    # Puerto del servidor de desarrollo
    case "$TECH" in
        react) DEFAULT_DEV_PORT=5173 ;;  # Vite
        vue) DEFAULT_DEV_PORT=5173 ;;    # Vite
        angular) DEFAULT_DEV_PORT=4200 ;;
        *) DEFAULT_DEV_PORT=3000 ;;
    esac
    
    read -rp "Puerto del servidor de desarrollo (sugerido: $DEFAULT_DEV_PORT): " DEV_PORT
    DEV_PORT=${DEV_PORT:-$DEFAULT_DEV_PORT}
    echo -e "${GREEN}✔ Puerto dev server: $DEV_PORT${NC}"
    
    # Puerto donde nginx escuchará
    SUGGESTED_PORT="80"
    read -rp "Puerto para nginx (sugerido: $SUGGESTED_PORT): " PORT
    PORT=${PORT:-$SUGGESTED_PORT}
    echo -e "${GREEN}✔ Puerto nginx: $PORT${NC}"
    
    ROOT_PATH="N/A (modo proxy)"
else
    # Modo archivos estáticos
    # Root path: /var/www/{provider}/{subdominio}/{dist si es SPA}
    if [ "$IS_SPA" = true ]; then
        SUGGESTED_ROOT="/var/www/$PROJECT/$SUBDOM_NAME/dist"
    elif [[ "$TECH" =~ ^(laravel|phalcon)$ ]]; then
        SUGGESTED_ROOT="/var/www/$PROJECT/$SUBDOM_NAME"
    else
        SUGGESTED_ROOT="/var/www/$PROJECT/$SUBDOM_NAME"
    fi
    
    read -rp "Root path (sugerido: $SUGGESTED_ROOT): " ROOT_PATH
    ROOT_PATH=${ROOT_PATH:-$SUGGESTED_ROOT}
    echo -e "${GREEN}✔ Root: $ROOT_PATH${NC}"
    
    # Puerto
    if [ "$ENVIRONMENT" = "prod" ]; then
        SUGGESTED_PORT="80"
    else
        SUGGESTED_PORT=$((8000 + RANDOM % 1000))
    fi
    
    read -rp "Puerto (sugerido: $SUGGESTED_PORT): " PORT
    PORT=${PORT:-$SUGGESTED_PORT}
    echo -e "${GREEN}✔ Puerto: $PORT${NC}"
    
    DEV_PORT="N/A"
fi

# ==================== PASO 7: Generar configuración ====================
echo -e "\n${BLUE}🔧 Generando configuración...${NC}"

SITE_NAME="${ENVIRONMENT}-${SUBDOM_NAME}-${TECH}"

# Crear archivo desde template
sed -e "s|{{DOMAIN}}|$DOMAIN|g" \
    -e "s|{{PORT}}|$PORT|g" \
    -e "s|{{ROOT_PATH}}|$ROOT_PATH|g" \
    -e "s|{{SITE_NAME}}|$SITE_NAME|g" \
    -e "s|{{DEV_PORT}}|$DEV_PORT|g" \
    "$PRESET_FILE" > "$OUTPUT_FILE"

echo -e "${GREEN}✔ Archivo creado: $OUTPUT_FILE${NC}"
echo -e "${BLUE}  Ruta relativa: $PROJECT/$ENVIRONMENT/$SUBDOM_NAME/$(basename $OUTPUT_FILE)${NC}"

# Crear archivo include principal si no existe
INCLUDE_FILE="$CONF_DIR/$PROJECT.conf"
if [ ! -f "$INCLUDE_FILE" ]; then
    cat > "$INCLUDE_FILE" << EOF
# Auto-generado - Include para todos los sitios de $PROJECT
# Nginx no soporta **, incluimos cada ambiente explícitamente
include /etc/nginx/conf.d/$PROJECT/dev/*/*.conf;
include /etc/nginx/conf.d/$PROJECT/qa/*/*.conf;
include /etc/nginx/conf.d/$PROJECT/prod/*/*.conf;
EOF
    echo -e "${GREEN}✔ Archivo include creado: $PROJECT.conf${NC}"
else
    echo -e "${GREEN}✔ Include ya existe: $PROJECT.conf${NC}"
fi

# Crear directorio root si no existe
mkdir -p "$ROOT_PATH"
chown -R www-data:www-data "$ROOT_PATH" 2>/dev/null || true
echo -e "${GREEN}✔ Directorio root creado: $ROOT_PATH${NC}"

# ==================== PASO 7: Validar ====================
echo -e "\n${BLUE}🧪 Esperando sincronización automática...${NC}"
sleep 4

if sudo nginx -t 2>&1 | tee /tmp/nginx-test.log; then
    echo -e "\n${GREEN}✅ Sitio creado exitosamente${NC}"
    echo -e "\n${BLUE}📋 Resumen:${NC}"
    echo -e "  Proyecto (provider): $PROJECT → $BASE_DOMAIN"
    echo -e "  Ambiente:            $ENVIRONMENT"
    echo -e "  Subdominio/App:      $SUBDOM_NAME"
    echo -e "  Dominio completo:    $DOMAIN"
    echo -e "  Tecnología:          $TECH"
    if [ "$USE_PROXY" = true ]; then
        echo -e "  Modo:                Proxy a dev server"
        echo -e "  Puerto nginx:        $PORT"
        echo -e "  Puerto dev server:   $DEV_PORT"
    else
        echo -e "  Modo:                Archivos estáticos"
        echo -e "  Puerto:              $PORT"
        echo -e "  Root:                $ROOT_PATH"
    fi
    echo -e "  Ruta config:         $PROJECT/$ENVIRONMENT/$SUBDOM_NAME/$(basename $OUTPUT_FILE)"
    echo ""
    echo -e "${YELLOW}💡 El daemon sincronizará automáticamente${NC}"
    echo -e "${YELLOW}💡 Nginx recargará en ~3 segundos${NC}"
    echo ""
    echo -e "${GREEN}🌐 Accede en:${NC}"
    echo -e "  http://$DOMAIN:$PORT"
    echo ""
    echo -e "${BLUE}📝 Siguiente paso (opcional):${NC}"
    echo -e "  sudo $SCRIPT_DIR/add-ssl.sh  # Agregar HTTPS"
else
    echo -e "\n${RED}❌ Error en la configuración${NC}"
    cat /tmp/nginx-test.log
    echo -e "\n${YELLOW}Archivo creado en: $OUTPUT_FILE${NC}"
    echo -e "${YELLOW}Revisa y corrige manualmente${NC}"
    exit 1
fi

rm -f /tmp/nginx-test.log

