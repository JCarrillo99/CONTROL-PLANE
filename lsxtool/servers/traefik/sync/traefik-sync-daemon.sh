#!/bin/bash
# =====================================================
# Script: traefik-sync-daemon.sh
# Autor: LSX
# Propósito: Monitorear y sincronizar cambios entre directorios Traefik
# =====================================================

set -eu
# No usamos trap ERR porque en WSL hay muchos falsos positivos con permisos

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Detectar rutas dinámicamente basándose en la ubicación del script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"  # /home/usuario/servers-install/traefik

# Buscar el archivo de configuración (puede ser traefik-dev.yml o traefik-prod.yml)
if [ -f "$BASE_DIR/config/traefik-dev.yml" ]; then
    CONFIG_SRC="$BASE_DIR/config/traefik-dev.yml"
elif [ -f "$BASE_DIR/config/traefik-prod.yml" ]; then
    CONFIG_SRC="$BASE_DIR/config/traefik-prod.yml"
else
    CONFIG_SRC="$BASE_DIR/config/traefik.yml"
fi
CONFIG_DEST="/etc/traefik/traefik.yml"
DYNAMIC_SRC="$BASE_DIR/config/dynamic"
DYNAMIC_DEST="/etc/traefik/dynamic"
CERTS_SRC="$BASE_DIR/config/certs"
CERTS_DEST="/certs"
LOG_FILE="/var/log/traefik-sync.log"
RELOAD_FLAG="/tmp/traefik-reload-flag"

# Array asociativo para debounce (evitar sincronizaciones duplicadas)
declare -A LAST_SYNC

# Función de log
log() {
    local msg="$1"
    local color="${2:-$NC}"
    echo -e "${color}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $msg" | tee -a "$LOG_FILE"
}

# Rotación automática de logs >1MB
if [ -f "$LOG_FILE" ] && [ "$(stat -c%s "$LOG_FILE")" -gt 1048576 ]; then
    mv "$LOG_FILE" "${LOG_FILE}.bak.$(date +%Y%m%d%H%M%S)"
fi
touch "$LOG_FILE"

# Validación de dependencias
if ! command -v inotifywait &>/dev/null; then
    log "❌ inotify-tools no está instalado. Ejecuta: sudo apt install inotify-tools" "$RED"
    exit 1
fi

if ! command -v rsync &>/dev/null; then
    log "❌ rsync no está instalado. Ejecuta: sudo apt install rsync" "$RED"
    exit 1
fi

# Sincroniza archivos de configuración
sync_file() {
    local file="$1"
    local src_dir dest_dir rel_path dest
    local now=$(date +%s)
    
    # Detectar tipo de archivo
    if [[ "$file" == "$CONFIG_SRC" ]]; then
        dest="$CONFIG_DEST"
        rel_path="traefik.yml"
    elif [[ "$file" == "$DYNAMIC_SRC"* ]]; then
        src_dir="$DYNAMIC_SRC"
        dest_dir="$DYNAMIC_DEST"
        rel_path="${file#$DYNAMIC_SRC/}"
        dest="$dest_dir/$rel_path"
    elif [[ "$file" == "$CERTS_SRC"* ]]; then
        src_dir="$CERTS_SRC"
        dest_dir="$CERTS_DEST"
        rel_path="${file#$CERTS_SRC/}"
        dest="$dest_dir/$rel_path"
    else
        return  # Archivo fuera de los directorios monitoreados
    fi
    
    # Ignorar archivos ocultos o temporales
    if [[ "$(basename "$file")" =~ ^\. ]] || [[ "$file" =~ (\.swp|\.tmp|\.part|~)$ ]]; then
        return
    fi

    # Debounce: evitar sincronizar el mismo archivo múltiples veces en 1 segundo
    local last_sync="${LAST_SYNC[$rel_path]:-0}"
    if (( now - last_sync < 1 )); then
        return  # Archivo sincronizado hace menos de 1 segundo, ignorar
    fi

    if [ -f "$file" ]; then
        mkdir -p "$(dirname "$dest")" 2>/dev/null || true
        # Copiar archivo y cambiar ownership a traefik:traefik
        set +e
        cp -f "$file" "$dest" 2>/dev/null
        # Forzar ownership a traefik:traefik (importante para seguridad)
        if id -u traefik >/dev/null 2>&1; then
            chown traefik:traefik "$dest" 2>/dev/null
        else
            chown root:root "$dest" 2>/dev/null
        fi
        chmod 644 "$dest" 2>/dev/null
        set -e
        
        # Actualizar timestamp de última sincronización
        LAST_SYNC[$rel_path]=$now
        
        log "📁 Sincronizado: $rel_path" "$GREEN"
        schedule_reload
    fi
}

# Elimina archivos eliminados en origen
delete_file() {
    local file="$1"
    local src_dir dest_dir rel_path dest
    
    # Detectar tipo de archivo
    if [[ "$file" == "$CONFIG_SRC" ]]; then
        # No eliminar el archivo principal de configuración
        return
    elif [[ "$file" == "$DYNAMIC_SRC"* ]]; then
        src_dir="$DYNAMIC_SRC"
        dest_dir="$DYNAMIC_DEST"
        rel_path="${file#$DYNAMIC_SRC/}"
        dest="$dest_dir/$rel_path"
    elif [[ "$file" == "$CERTS_SRC"* ]]; then
        # No eliminar certificados automáticamente (muy peligroso)
        return
    else
        return
    fi
    
    if [ -f "$dest" ]; then
        rm -f "$dest"
        log "🗑️  Archivo eliminado: $rel_path" "$YELLOW"
        schedule_reload
    fi
}

# Marca que se requiere recarga
schedule_reload() {
    touch "$RELOAD_FLAG"
}

# Hilo que recarga traefik si hay bandera
monitor_reload() {
    while true; do
        if [ -f "$RELOAD_FLAG" ]; then
            sleep 2  # Debounce de cambios múltiples
            rm -f "$RELOAD_FLAG"
            if systemctl is-active --quiet traefik; then
                systemctl reload traefik
                log "🔄 Recarga acumulada de Traefik completada" "$BLUE"
            else
                log "⚠️  Traefik no está activo, no se recarga" "$YELLOW"
            fi
        fi
        sleep 1
    done
}

# Sincronización inicial completa
log "🚀 Iniciando sincronización inicial..." "$BLUE"

# En WSL usamos cp en lugar de rsync para evitar problemas con permisos
if grep -qi microsoft /proc/version 2>/dev/null; then
    log "Detectado WSL - usando cp para sincronización" "$YELLOW"
    # Copiar configuración principal
    if [ -f "$CONFIG_SRC" ]; then
        cp -f "$CONFIG_SRC" "$CONFIG_DEST" 2>/dev/null || true
        if id -u traefik >/dev/null 2>&1; then
            chown traefik:traefik "$CONFIG_DEST" 2>/dev/null || true
        else
            chown root:root "$CONFIG_DEST" 2>/dev/null || true
        fi
        chmod 644 "$CONFIG_DEST" 2>/dev/null || true
    fi
    # Copiar dynamic
    if [ -d "$DYNAMIC_SRC" ]; then
        cp -rf "$DYNAMIC_SRC"/* "$DYNAMIC_DEST/" 2>/dev/null || true
    fi
    # Copiar certificados (si existen)
    if [ -d "$CERTS_SRC" ] && [ "$(ls -A "$CERTS_SRC" 2>/dev/null)" ]; then
        cp -f "$CERTS_SRC"/* "$CERTS_DEST/" 2>/dev/null || true
    fi
else
    # En Linux nativo usamos rsync
    if [ -f "$CONFIG_SRC" ]; then
        rsync -av "$CONFIG_SRC" "$CONFIG_DEST" >> "$LOG_FILE" 2>&1
    fi
    if [ -d "$DYNAMIC_SRC" ]; then
        rsync -av --delete "$DYNAMIC_SRC/" "$DYNAMIC_DEST/" >> "$LOG_FILE" 2>&1
    fi
    if [ -d "$CERTS_SRC" ] && [ "$(ls -A "$CERTS_SRC" 2>/dev/null)" ]; then
        rsync -av "$CERTS_SRC/" "$CERTS_DEST/" >> "$LOG_FILE" 2>&1
    fi
fi

# Cambiar ownership de todos los archivos
for dir in "$DYNAMIC_DEST" "$CERTS_DEST"; do
    if [ -d "$dir" ]; then
        if id -u traefik >/dev/null 2>&1; then
            find "$dir" -type f -exec chown traefik:traefik {} \; 2>/dev/null || true
            find "$dir" -type d -exec chown traefik:traefik {} \; 2>/dev/null || true
        else
            find "$dir" -type f -exec chown root:root {} \; 2>/dev/null || true
            find "$dir" -type d -exec chown root:root {} \; 2>/dev/null || true
        fi
        find "$dir" -type f -exec chmod 644 {} \; 2>/dev/null || true
    fi
done

if [ -f "$CONFIG_DEST" ]; then
    if id -u traefik >/dev/null 2>&1; then
        chown traefik:traefik "$CONFIG_DEST" 2>/dev/null || true
    else
        chown root:root "$CONFIG_DEST" 2>/dev/null || true
    fi
    chmod 644 "$CONFIG_DEST" 2>/dev/null || true
fi

log "✅ Sincronización inicial completada (traefik.yml + dynamic + certs)" "$GREEN"

# Inicia hilo de recarga
monitor_reload &

# Monitoreo en tiempo real
log "👀 Escuchando cambios en:" "$YELLOW"
log "   - traefik.yml: $CONFIG_SRC" "$YELLOW"
log "   - dynamic: $DYNAMIC_SRC" "$YELLOW"
if [ -d "$CERTS_SRC" ]; then
    log "   - certs: $CERTS_SRC" "$YELLOW"
fi

# Detectar si estamos en WSL
if grep -qi microsoft /proc/version 2>/dev/null; then
    log "⚠️  WSL detectado - inotify NO funciona en /mnt/c/" "$YELLOW"
    log "🔧 Usando polling optimizado (solo sincroniza archivos modificados)" "$BLUE"
    
    # Array asociativo para guardar hash de cada archivo
    declare -A FILE_HASHES
    
    # Generar hashes iniciales
    for src_file in "$CONFIG_SRC" "$DYNAMIC_SRC" "$CERTS_SRC"; do
        if [ -f "$src_file" ] && [ -n "$src_file" ]; then
            hash=$(md5sum "$src_file" 2>/dev/null | awk '{print $1}')
            FILE_HASHES["$src_file"]="$hash"
        elif [ -d "$src_file" ] && [ -n "$src_file" ]; then
            while IFS= read -r file; do
                hash=$(md5sum "$file" 2>/dev/null | awk '{print $1}')
                FILE_HASHES["$file"]="$hash"
            done < <(find "$src_file" -type f \( -name "*.yml" -o -name "*.yaml" -o -name "*.crt" -o -name "*.key" \) 2>/dev/null)
        fi
    done
    
    # Loop de polling optimizado
    while true; do
        sleep 3
        
        # Revisar configuración principal
        if [ -f "$CONFIG_SRC" ]; then
            current_hash=$(md5sum "$CONFIG_SRC" 2>/dev/null | awk '{print $1}')
            previous_hash="${FILE_HASHES[$CONFIG_SRC]}"
            if [ "$current_hash" != "$previous_hash" ]; then
                sync_file "$CONFIG_SRC"
                FILE_HASHES["$CONFIG_SRC"]="$current_hash"
            fi
        fi
        
        # Revisar archivos en dynamic y certs
        for src_dir in "$DYNAMIC_SRC" "$CERTS_SRC"; do
            if [ -d "$src_dir" ]; then
                while IFS= read -r file; do
                    current_hash=$(md5sum "$file" 2>/dev/null | awk '{print $1}')
                    previous_hash="${FILE_HASHES[$file]}"
                    
                    # Si el hash cambió, sincronizar SOLO ese archivo
                    if [ "$current_hash" != "$previous_hash" ]; then
                        sync_file "$file"
                        FILE_HASHES["$file"]="$current_hash"
                    fi
                done < <(find "$src_dir" -type f \( -name "*.yml" -o -name "*.yaml" -o -name "*.crt" -o -name "*.key" \) 2>/dev/null)
            fi
        done
    done
else
    # Linux nativo - usar inotify (más eficiente)
    log "🔧 Usando inotify - detección instantánea" "$GREEN"
    
    # Monitorear configuración principal
    if [ -f "$CONFIG_SRC" ]; then
        inotifywait -m -e modify,close_write "$CONFIG_SRC" --format '%w%f %e' |
        while read -r file event; do
            sync_file "$file"
        done &
    fi
    
    # Monitorear dynamic y certs
    for src_dir in "$DYNAMIC_SRC" "$CERTS_SRC"; do
        if [ -d "$src_dir" ]; then
            inotifywait -m -r -e create,modify,delete,move,close_write "$src_dir" --format '%w%f %e' |
            while read -r file event; do
                case "$event" in
                    *CREATE*|*MODIFY*|*CLOSE_WRITE*|*MOVED_TO*)
                        sync_file "$file"
                        ;;
                    *DELETE*|*MOVED_FROM*)
                        delete_file "$file"
                        ;;
                    *)
                        ;;
                esac
            done &
        fi
    done
    
    # Esperar a todos los procesos
    wait
fi

