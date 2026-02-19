#!/bin/bash
# =====================================================
# Script: nginx-sync-daemon.sh
# Autor: LSX
# Propósito: Monitorear y sincronizar cambios entre directorios Nginx
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
BASE_DIR="$(dirname "$SCRIPT_DIR")"  # /home/usuario/servers-install/nginx

CONF_SRC="$BASE_DIR/configuration/etc/nginx/conf.d"
CONF_DEST="/etc/nginx/conf.d"
SNIPPETS_SRC="$BASE_DIR/configuration/etc/nginx/snippets"
SNIPPETS_DEST="/etc/nginx/snippets"
SITES_AVAILABLE_SRC="$BASE_DIR/configuration/etc/nginx/sites-available"
SITES_AVAILABLE_DEST="/etc/nginx/sites-available"
SITES_ENABLED_SRC="$BASE_DIR/configuration/etc/nginx/sites-enabled"
SITES_ENABLED_DEST="/etc/nginx/sites-enabled"
LOG_FILE="/var/log/nginx-sync.log"
RELOAD_FLAG="/tmp/nginx-reload-flag"

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

# Sincroniza un archivo individual
sync_file() {
    local file="$1"
    local src_dir dest_dir rel_path dest
    local now=$(date +%s)
    
    # Detectar tipo de archivo
    if [[ "$file" == "$CONF_SRC"* ]]; then
        src_dir="$CONF_SRC"
        dest_dir="$CONF_DEST"
        rel_path="${file#$CONF_SRC/}"
    elif [[ "$file" == "$SNIPPETS_SRC"* ]]; then
        src_dir="$SNIPPETS_SRC"
        dest_dir="$SNIPPETS_DEST"
        rel_path="${file#$SNIPPETS_SRC/}"
    elif [[ "$file" == "$SITES_AVAILABLE_SRC"* ]]; then
        src_dir="$SITES_AVAILABLE_SRC"
        dest_dir="$SITES_AVAILABLE_DEST"
        rel_path="${file#$SITES_AVAILABLE_SRC/}"
    elif [[ "$file" == "$SITES_ENABLED_SRC"* ]]; then
        # sites-enabled se sincroniza directamente (igual que conf.d)
        src_dir="$SITES_ENABLED_SRC"
        dest_dir="$SITES_ENABLED_DEST"
        rel_path="${file#$SITES_ENABLED_SRC/}"
    else
        return  # Archivo fuera de los directorios monitoreados
    fi
    
    dest="$dest_dir/$rel_path"
    
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
        # Eliminar enlace simbólico si existe (especialmente en sites-enabled)
        [ -L "$dest" ] && rm -f "$dest" 2>/dev/null || true
        # Copiar archivo y cambiar ownership a root:root
        set +e
        cp -f "$file" "$dest" 2>/dev/null
        # Forzar ownership a root:root (importante para seguridad)
        chown root:root "$dest" 2>/dev/null
        chmod 644 "$dest" 2>/dev/null
        set -e
        
        # Actualizar timestamp de última sincronización
        LAST_SYNC[$rel_path]=$now
        
        log "📁 Sincronizado: $rel_path (root:root)" "$GREEN"
        schedule_reload
    fi
}

# Elimina archivos eliminados en origen
delete_file() {
    local file="$1"
    local src_dir dest_dir rel_path dest
    
    # Detectar tipo de archivo
    if [[ "$file" == "$CONF_SRC"* ]]; then
        src_dir="$CONF_SRC"
        dest_dir="$CONF_DEST"
        rel_path="${file#$CONF_SRC/}"
    elif [[ "$file" == "$SNIPPETS_SRC"* ]]; then
        src_dir="$SNIPPETS_SRC"
        dest_dir="$SNIPPETS_DEST"
        rel_path="${file#$SNIPPETS_SRC/}"
    elif [[ "$file" == "$SITES_AVAILABLE_SRC"* ]]; then
        src_dir="$SITES_AVAILABLE_SRC"
        dest_dir="$SITES_AVAILABLE_DEST"
        rel_path="${file#$SITES_AVAILABLE_SRC/}"
    elif [[ "$file" == "$SITES_ENABLED_SRC"* ]]; then
        src_dir="$SITES_ENABLED_SRC"
        dest_dir="$SITES_ENABLED_DEST"
        rel_path="${file#$SITES_ENABLED_SRC/}"
    else
        return
    fi
    
    dest="$dest_dir/$rel_path"

    if [ -f "$dest" ] || [ -L "$dest" ]; then
        rm -f "$dest"
        log "🗑️  Archivo/enlace eliminado: $rel_path" "$YELLOW"
        schedule_reload
    fi
}

# Marca que se requiere recarga
schedule_reload() {
    touch "$RELOAD_FLAG"
}

# Hilo que recarga nginx si hay bandera
monitor_reload() {
    while true; do
        if [ -f "$RELOAD_FLAG" ]; then
            sleep 2  # Debounce de cambios múltiples
            rm -f "$RELOAD_FLAG"
            if nginx -t &>/dev/null; then
                systemctl reload nginx
                log "🔄 Recarga acumulada de Nginx completada" "$BLUE"
            else
                log "❌ Error en prueba de configuración, no se recarga Nginx" "$RED"
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
    # Copiar conf.d
    [ -d "$CONF_SRC" ] && cp -rf "$CONF_SRC"/* "$CONF_DEST/" 2>/dev/null || true
    # Copiar snippets
    [ -d "$SNIPPETS_SRC" ] && cp -rf "$SNIPPETS_SRC"/* "$SNIPPETS_DEST/" 2>/dev/null || true
    # Copiar sites-available
    [ -d "$SITES_AVAILABLE_SRC" ] && cp -rf "$SITES_AVAILABLE_SRC"/* "$SITES_AVAILABLE_DEST/" 2>/dev/null || true
    # Copiar sites-enabled (directamente, sin enlaces)
    [ -d "$SITES_ENABLED_SRC" ] && cp -rf "$SITES_ENABLED_SRC"/* "$SITES_ENABLED_DEST/" 2>/dev/null || true
    
    # Eliminar archivos huérfanos en WSL (que no existen en el directorio local)
    # Para cada directorio, eliminar archivos .conf que no existen en el origen
    cleanup_orphans() {
        local s_dir="$1"
        local d_dir="$2"
        [ -d "$s_dir" ] && [ -d "$d_dir" ] || return
        while IFS= read -r dest_file; do
            rel_path="${dest_file#$d_dir/}"
            src_file="$s_dir/$rel_path"
            # Si el archivo no existe en el origen, eliminarlo del destino
            if [ ! -f "$src_file" ] && [[ "$dest_file" =~ \.(conf)$ ]]; then
                rm -f "$dest_file" 2>/dev/null && log "🗑️  Archivo huérfano eliminado: $rel_path" "$YELLOW" || true
            fi
        done < <(find "$d_dir" -type f -name "*.conf" 2>/dev/null)
    }
    cleanup_orphans "$CONF_SRC" "$CONF_DEST"
    cleanup_orphans "$SNIPPETS_SRC" "$SNIPPETS_DEST"
    cleanup_orphans "$SITES_AVAILABLE_SRC" "$SITES_AVAILABLE_DEST"
    cleanup_orphans "$SITES_ENABLED_SRC" "$SITES_ENABLED_DEST"
else
    # En Linux nativo usamos rsync (con --delete para eliminar archivos huérfanos)
    [ -d "$CONF_SRC" ] && rsync -av --delete "$CONF_SRC/" "$CONF_DEST/" >> "$LOG_FILE" 2>&1
    [ -d "$SNIPPETS_SRC" ] && rsync -av --delete "$SNIPPETS_SRC/" "$SNIPPETS_DEST/" >> "$LOG_FILE" 2>&1
    [ -d "$SITES_AVAILABLE_SRC" ] && rsync -av --delete "$SITES_AVAILABLE_SRC/" "$SITES_AVAILABLE_DEST/" >> "$LOG_FILE" 2>&1
    [ -d "$SITES_ENABLED_SRC" ] && rsync -av --delete "$SITES_ENABLED_SRC/" "$SITES_ENABLED_DEST/" >> "$LOG_FILE" 2>&1
fi

# Cambiar ownership de todos los archivos a root:root
for dir in "$CONF_DEST" "$SNIPPETS_DEST" "$SITES_AVAILABLE_DEST" "$SITES_ENABLED_DEST"; do
    [ -d "$dir" ] && find "$dir" -type f -exec chown root:root {} \; 2>/dev/null
    [ -d "$dir" ] && find "$dir" -type d -exec chown root:root {} \; 2>/dev/null
    [ -d "$dir" ] && find "$dir" -type f -exec chmod 644 {} \; 2>/dev/null
done

log "✅ Sincronización inicial completada (conf.d + snippets + sites-available + sites-enabled) - permisos root:root" "$GREEN"

# Inicia hilo de recarga
monitor_reload &

# Monitoreo en tiempo real
log "👀 Escuchando cambios en:" "$YELLOW"
log "   - conf.d: $CONF_SRC" "$YELLOW"
log "   - snippets: $SNIPPETS_SRC" "$YELLOW"
[ -d "$SITES_AVAILABLE_SRC" ] && log "   - sites-available: $SITES_AVAILABLE_SRC" "$YELLOW"
[ -d "$SITES_ENABLED_SRC" ] && log "   - sites-enabled: $SITES_ENABLED_SRC" "$YELLOW"

# Detectar si estamos en WSL
if grep -qi microsoft /proc/version 2>/dev/null; then
    log "⚠️  WSL detectado - inotify NO funciona en /mnt/c/" "$YELLOW"
    log "🔧 Usando polling optimizado (solo sincroniza archivos modificados)" "$BLUE"
    
    # Array asociativo para guardar hash de cada archivo
    declare -A FILE_HASHES
    
    # Generar hashes iniciales de todos los directorios
    for src_dir in "$CONF_SRC" "$SNIPPETS_SRC" "$SITES_AVAILABLE_SRC" "$SITES_ENABLED_SRC"; do
        [ -d "$src_dir" ] || continue
        while IFS= read -r file; do
            hash=$(md5sum "$file" 2>/dev/null | awk '{print $1}')
            FILE_HASHES["$file"]="$hash"
        done < <(find "$src_dir" -type f \( -name "*.conf" -o -name "*" \) 2>/dev/null)
    done
    
    # Loop de polling optimizado
    while true; do
        sleep 3
        
        # Revisar archivos en todos los directorios
        for src_dir in "$CONF_SRC" "$SNIPPETS_SRC" "$SITES_AVAILABLE_SRC" "$SITES_ENABLED_SRC"; do
            [ -d "$src_dir" ] || continue
            while IFS= read -r file; do
                current_hash=$(md5sum "$file" 2>/dev/null | awk '{print $1}')
                previous_hash="${FILE_HASHES[$file]}"
                
                # Si el hash cambió, sincronizar SOLO ese archivo
                if [ "$current_hash" != "$previous_hash" ]; then
                    sync_file "$file"
                    FILE_HASHES["$file"]="$current_hash"
                fi
            done < <(find "$src_dir" -type f \( -name "*.conf" -o -name "*" \) 2>/dev/null)
        done
    done
else
    # Linux nativo - usar inotify (más eficiente) para todos los directorios
    log "🔧 Usando inotify - detección instantánea" "$GREEN"
    WATCH_DIRS=("$CONF_SRC" "$SNIPPETS_SRC")
    [ -d "$SITES_AVAILABLE_SRC" ] && WATCH_DIRS+=("$SITES_AVAILABLE_SRC")
    [ -d "$SITES_ENABLED_SRC" ] && WATCH_DIRS+=("$SITES_ENABLED_SRC")
    
    inotifywait -m -r -e create,modify,delete,move,close_write "${WATCH_DIRS[@]}" --format '%w%f %e' |
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
    done
fi


