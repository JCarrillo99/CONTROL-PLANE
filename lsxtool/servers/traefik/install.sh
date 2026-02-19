#!/bin/bash
# Script de instalación de Traefik para LunarCore GNU/Linux (Debian Bookworm)

set -e  # Salir si hay algún error

# Obtener el directorio del script
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Variables
TRAEFIK_VERSION="v3.2.0"  # Actualiza esta versión según necesites
TRAEFIK_DIR="/opt/traefik"
TRAEFIK_CONFIG_DIR="/etc/traefik"
TRAEFIK_LOG_DIR="/var/log/traefik"
TRAEFIK_BIN="/usr/local/bin/traefik"
TRAEFIK_USER="traefik"
TRAEFIK_SERVICE="/etc/systemd/system/traefik.service"

echo -e "${GREEN}=== Instalador de Traefik para LunarCore ===${NC}"
echo ""

# Verificar si se ejecuta como root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}❌ Este script debe ejecutarse como root (usa sudo)${NC}"
    exit 1
fi

# Detectar arquitectura
ARCH=$(uname -m)
case $ARCH in
    x86_64)
        TRAEFIK_ARCH="amd64"
        ;;
    aarch64|arm64)
        TRAEFIK_ARCH="arm64"
        ;;
    armv7l)
        TRAEFIK_ARCH="armv7"
        ;;
    *)
        echo -e "${RED}❌ Arquitectura no soportada: $ARCH${NC}"
        exit 1
        ;;
esac

echo -e "${YELLOW}[1/9]${NC} Detectando sistema..."
echo "  - Distribución: LunarCore GNU/Linux (Debian Bookworm)"
echo "  - Arquitectura: $ARCH ($TRAEFIK_ARCH)"
echo ""

# Actualizar repositorios e instalar dependencias
echo -e "${YELLOW}[2/9]${NC} Instalando dependencias..."
apt-get update -qq
apt-get install -y wget curl ca-certificates

# Crear usuario para Traefik si no existe
echo -e "${YELLOW}[3/9]${NC} Creando usuario del sistema para Traefik..."
if ! id -u $TRAEFIK_USER > /dev/null 2>&1; then
    useradd --system --no-create-home --shell /bin/false $TRAEFIK_USER
    echo "  ✓ Usuario '$TRAEFIK_USER' creado"
else
    echo "  ✓ Usuario '$TRAEFIK_USER' ya existe"
fi

# Crear directorios necesarios
echo -e "${YELLOW}[4/9]${NC} Creando directorios..."
mkdir -p $TRAEFIK_DIR
mkdir -p $TRAEFIK_CONFIG_DIR
mkdir -p $TRAEFIK_CONFIG_DIR/dynamic
mkdir -p $TRAEFIK_LOG_DIR
chown -R $TRAEFIK_USER:$TRAEFIK_USER $TRAEFIK_DIR
chown -R $TRAEFIK_USER:$TRAEFIK_USER $TRAEFIK_LOG_DIR

# Descargar Traefik
echo -e "${YELLOW}[5/9]${NC} Descargando Traefik ${TRAEFIK_VERSION}..."
DOWNLOAD_URL="https://github.com/traefik/traefik/releases/download/${TRAEFIK_VERSION}/traefik_${TRAEFIK_VERSION}_linux_${TRAEFIK_ARCH}.tar.gz"
echo "  URL: $DOWNLOAD_URL"

cd /tmp
if wget -q --show-progress "$DOWNLOAD_URL" -O traefik.tar.gz; then
    echo "  ✓ Descarga completada"
else
    echo -e "${RED}❌ Error al descargar Traefik${NC}"
    exit 1
fi

# Extraer y mover binario
echo -e "${YELLOW}[6/9]${NC} Instalando binario..."
tar -xzf traefik.tar.gz
mv traefik $TRAEFIK_BIN
chmod +x $TRAEFIK_BIN
rm traefik.tar.gz
echo "  ✓ Binario instalado en $TRAEFIK_BIN"

# Dar permisos para usar puertos privilegiados (<1024)
echo "  ✓ Configurando permisos para puertos privilegiados..."
setcap 'cap_net_bind_service=+ep' $TRAEFIK_BIN

# Verificar instalación
INSTALLED_VERSION=$($TRAEFIK_BIN version | head -n 1)
echo "  ✓ Versión instalada: $INSTALLED_VERSION"

# Copiar archivos de configuración
echo -e "${YELLOW}[7/9]${NC} Copiando configuración..."

# Usar ruta desde el directorio del script
CONFIG_SOURCE="$SCRIPT_DIR/config"

# Verificar que exista la carpeta de configuración
if [ ! -d "$CONFIG_SOURCE" ]; then
    echo -e "${RED}❌ No se encontró la carpeta de configuración en: $CONFIG_SOURCE${NC}"
    exit 1
fi

# Copiar configuración principal (desarrollo)
if [ -f "$CONFIG_SOURCE/traefik-dev.yml" ]; then
    cp "$CONFIG_SOURCE/traefik-dev.yml" "$TRAEFIK_CONFIG_DIR/traefik.yml"
    echo "  ✓ Configuración principal copiada (traefik-dev.yml)"
else
    echo -e "${RED}❌ No se encontró traefik-dev.yml${NC}"
    exit 1
fi

# Copiar configuraciones dinámicas
if [ -d "$CONFIG_SOURCE/dynamic" ]; then
    cp -r "$CONFIG_SOURCE/dynamic/"* "$TRAEFIK_CONFIG_DIR/dynamic/"
    echo "  ✓ Configuraciones dinámicas copiadas"
else
    echo -e "${RED}❌ No se encontró la carpeta dynamic${NC}"
    exit 1
fi

# Crear directorio para certificados ACME si no existe
mkdir -p /acme
if [ -d "$CONFIG_SOURCE/acme" ]; then
    # Copiar archivos de ejemplo ACME si existen
    cp -n "$CONFIG_SOURCE/acme/"*.json /acme/ 2>/dev/null || true
    echo "  ✓ Directorio ACME creado (con archivos de ejemplo)"
else
    echo "  ✓ Directorio ACME creado"
fi
chown -R $TRAEFIK_USER:$TRAEFIK_USER /acme

# Crear directorio para certificados SSL si no existe
mkdir -p /certs
if [ -d "$CONFIG_SOURCE/certs" ]; then
    # Copiar certificados si existen
    if ls "$CONFIG_SOURCE/certs/"* 1> /dev/null 2>&1; then
        cp "$CONFIG_SOURCE/certs/"* /certs/ 2>/dev/null || true
        echo "  ✓ Directorio para certificados creado (certificados copiados)"
    else
        echo "  ✓ Directorio para certificados creado"
    fi
else
    echo "  ✓ Directorio para certificados creado"
fi
chown -R $TRAEFIK_USER:$TRAEFIK_USER /certs

chown -R $TRAEFIK_USER:$TRAEFIK_USER $TRAEFIK_CONFIG_DIR
echo "  ✓ Permisos configurados en $TRAEFIK_CONFIG_DIR"

# Crear servicio systemd
echo -e "${YELLOW}[8/9]${NC} Creando servicio systemd..."
cat > $TRAEFIK_SERVICE <<EOF
[Unit]
Description=Traefik - The Cloud Native Edge Router
Documentation=https://doc.traefik.io/traefik/
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$TRAEFIK_USER
Group=$TRAEFIK_USER
ExecStart=$TRAEFIK_BIN --configFile=$TRAEFIK_CONFIG_DIR/traefik.yml
Restart=on-failure
RestartSec=5s
LimitNOFILE=65535

# Capabilities para usar puertos privilegiados
AmbientCapabilities=CAP_NET_BIND_SERVICE
CapabilityBoundingSet=CAP_NET_BIND_SERVICE

# Seguridad
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true
ReadWritePaths=$TRAEFIK_LOG_DIR

[Install]
WantedBy=multi-user.target
EOF

echo "  ✓ Servicio systemd creado"

# Habilitar e iniciar servicio
echo -e "${YELLOW}[9/9]${NC} Configurando servicio..."
systemctl daemon-reload
systemctl enable traefik
systemctl start traefik

# Verificar estado
sleep 2
if systemctl is-active --quiet traefik; then
    echo -e "${GREEN}✓ Traefik instalado y ejecutándose correctamente${NC}"
else
    echo -e "${YELLOW}⚠ Traefik instalado pero no está ejecutándose${NC}"
    echo "  Verifica los logs con: journalctl -u traefik -f"
fi

echo ""
echo -e "${GREEN}=== Instalación completada ===${NC}"
echo ""
echo "Comandos útiles:"
echo "  - Ver estado:       systemctl status traefik"
echo "  - Ver logs:         journalctl -u traefik -f"
echo "  - Reiniciar:        systemctl restart traefik"
echo "  - Detener:          systemctl stop traefik"
echo "  - Configuración:    $TRAEFIK_CONFIG_DIR"
echo "  - Logs:             $TRAEFIK_LOG_DIR"
echo ""
echo -e "${GREEN}Dashboard de Traefik:${NC}"
echo "  - URL HTTP:         http://dev-domains-170.lunarsystemx.com/"
echo "  - URL HTTPS:        https://dev-domains-170.lunarsystemx.com/"
echo "  - Usuario:          admin"
echo "  - Contraseña:       TuContraseñaSegura"
echo ""
echo -e "${YELLOW}IMPORTANTE:${NC}"
echo "  1. Asegúrate de que el dominio dev-domains-170.lunarsystemx.com apunte a este servidor"
echo "  2. Configuración principal: $TRAEFIK_CONFIG_DIR/traefik.yml"
echo "  3. Configuraciones dinámicas: $TRAEFIK_CONFIG_DIR/dynamic/"
echo "  4. Para cambiar la contraseña, edita: $TRAEFIK_CONFIG_DIR/dynamic/02-middlewares.yml"
echo "  5. Los certificados SSL deben colocarse en: /certs/"
echo ""

