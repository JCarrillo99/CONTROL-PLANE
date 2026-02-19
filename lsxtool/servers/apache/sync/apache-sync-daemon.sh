#!/bin/bash
# =====================================================
# Script: apache-sync-daemon.sh
# Autor: LSX
# Propósito: Monitorear y sincronizar cambios entre directorios Apache
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
BASE_DIR="$(dirname "$SCRIPT_DIR")"  # /home/usuario/servers-install/apache
CONFIG_DIR="$BASE_DIR/configuration/etc/apache2"

SITES_AVAILABLE_SRC="$CONFIG_DIR/sites-available"
SITES_AVAILABLE_DEST="/etc/apache2/sites-available"
SITES_ENABLED_SRC="$CONFIG_DIR/sites-enabled"
SITES_ENABLED_DEST="/etc/apache2/sites-enabled"
CONF_AVAILABLE_SRC="$CONFIG_DIR/conf-available"
CONF_AVAILABLE_DEST="/etc/apache2/conf-available"
CONF_ENABLED_SRC="$CONFIG_DIR/conf-enabled"
CONF_ENABLED_DEST="/etc/apache2/conf-enabled"
MODS_AVAILABLE_SRC="$CONFIG_DIR/mods-available"
MODS_AVAILABLE_DEST="/etc/apache2/mods-available"
MODS_ENABLED_SRC="$CONFIG_DIR/mods-enabled"
MODS_ENABLED_DEST="/etc/apache2/mods-enabled"
PORTS_CONF_SRC="$CONFIG_DIR/ports.conf"
PORTS_CONF_DEST="/etc/apache2/ports.conf"
LOG_FILE="/var/log/apache-sync.log"
RELOAD_FLAG="/tmp/apache-reload-flag"

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
    if [[ "$file" == "$PORTS_CONF_SRC" ]]; then
        # ports.conf es un archivo especial en la raíz de apache2
        dest="$PORTS_CONF_DEST"
        if [ -f "$file" ]; then
            cp -f "$file" "$dest" 2>/dev/null
            chown root:root "$dest" 2>/dev/null
            chmod 644 "$dest" 2>/dev/null
            log "📁 Sincronizado: ports.conf (root:root)" "$GREEN"
            schedule_reload
        fi
        return
    elif [[ "$file" == "$SITES_AVAILABLE_SRC"* ]]; then
        src_dir="$SITES_AVAILABLE_SRC"
        dest_dir="$SITES_AVAILABLE_DEST"
        rel_path="${file#$SITES_AVAILABLE_SRC/}"
    elif [[ "$file" == "$SITES_ENABLED_SRC"* ]]; then
        src_dir="$SITES_ENABLED_SRC"
        dest_dir="$SITES_ENABLED_DEST"
        rel_path="${file#$SITES_ENABLED_SRC/}"
    elif [[ "$file" == "$CONF_AVAILABLE_SRC"* ]]; then
        src_dir="$CONF_AVAILABLE_SRC"
        dest_dir="$CONF_AVAILABLE_DEST"
        rel_path="${file#$CONF_AVAILABLE_SRC/}"
    elif [[ "$file" == "$CONF_ENABLED_SRC"* ]]; then
        src_dir="$CONF_ENABLED_SRC"
        dest_dir="$CONF_ENABLED_DEST"
        rel_path="${file#$CONF_ENABLED_SRC/}"
    elif [[ "$file" == "$MODS_AVAILABLE_SRC"* ]]; then
        src_dir="$MODS_AVAILABLE_SRC"
        dest_dir="$MODS_AVAILABLE_DEST"
        rel_path="${file#$MODS_AVAILABLE_SRC/}"
    elif [[ "$file" == "$MODS_ENABLED_SRC"* ]]; then
        src_dir="$MODS_ENABLED_SRC"
        dest_dir="$MODS_ENABLED_DEST"
        rel_path="${file#$MODS_ENABLED_SRC/}"
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

    if [ -f "$file" ] || [ -L "$file" ]; then
        mkdir -p "$(dirname "$dest")" 2>/dev/null || true
        # Eliminar archivo/symlink existente
        [ -e "$dest" ] && rm -f "$dest" 2>/dev/null || true
        
        set +e
        # Si es un symlink, preservarlo como symlink
        if [ -L "$file" ]; then
            # Leer el destino del symlink y crear uno nuevo
            link_target=$(readlink "$file")
            # Si es relativo, ajustar la ruta
            if [[ "$link_target" != /* ]]; then
                # Symlink relativo: mantener la misma estructura
                ln -sf "$link_target" "$dest" 2>/dev/null
            else
                # Symlink absoluto: convertir a relativo si es posible
                # Para sites-enabled, normalmente apuntan a ../sites-available/
                if [[ "$link_target" == *"/sites-available/"* ]]; then
                    ln -sf "../sites-available/$(basename "$link_target")" "$dest" 2>/dev/null
                else
                    ln -sf "$link_target" "$dest" 2>/dev/null
                fi
            fi
        else
            # Archivo regular: copiar normalmente
            cp -f "$file" "$dest" 2>/dev/null
        fi
        # Forzar ownership a root:root (importante para seguridad)
        chown -h root:root "$dest" 2>/dev/null
        [ ! -L "$dest" ] && chmod 644 "$dest" 2>/dev/null || true
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
    if [[ "$file" == "$SITES_AVAILABLE_SRC"* ]]; then
        src_dir="$SITES_AVAILABLE_SRC"
        dest_dir="$SITES_AVAILABLE_DEST"
        rel_path="${file#$SITES_AVAILABLE_SRC/}"
    elif [[ "$file" == "$SITES_ENABLED_SRC"* ]]; then
        src_dir="$SITES_ENABLED_SRC"
        dest_dir="$SITES_ENABLED_DEST"
        rel_path="${file#$SITES_ENABLED_SRC/}"
    elif [[ "$file" == "$CONF_AVAILABLE_SRC"* ]]; then
        src_dir="$CONF_AVAILABLE_SRC"
        dest_dir="$CONF_AVAILABLE_DEST"
        rel_path="${file#$CONF_AVAILABLE_SRC/}"
    elif [[ "$file" == "$CONF_ENABLED_SRC"* ]]; then
        src_dir="$CONF_ENABLED_SRC"
        dest_dir="$CONF_ENABLED_DEST"
        rel_path="${file#$CONF_ENABLED_SRC/}"
    elif [[ "$file" == "$MODS_AVAILABLE_SRC"* ]]; then
        src_dir="$MODS_AVAILABLE_SRC"
        dest_dir="$MODS_AVAILABLE_DEST"
        rel_path="${file#$MODS_AVAILABLE_SRC/}"
    elif [[ "$file" == "$MODS_ENABLED_SRC"* ]]; then
        src_dir="$MODS_ENABLED_SRC"
        dest_dir="$MODS_ENABLED_DEST"
        rel_path="${file#$MODS_ENABLED_SRC/}"
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

# Hilo que recarga apache si hay bandera
monitor_reload() {
    while true; do
        if [ -f "$RELOAD_FLAG" ]; then
            sleep 2  # Debounce de cambios múltiples
            rm -f "$RELOAD_FLAG"
            if apache2ctl configtest >/dev/null 2>&1; then
                systemctl reload apache2
                log "🔄 Recarga acumulada de Apache completada" "$BLUE"
            else
                log "❌ Error en prueba de configuración, no se recarga Apache" "$RED"
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
    # Copiar ports.conf primero
    [ -f "$PORTS_CONF_SRC" ] && cp -f "$PORTS_CONF_SRC" "$PORTS_CONF_DEST" 2>/dev/null && chown root:root "$PORTS_CONF_DEST" 2>/dev/null && chmod 644 "$PORTS_CONF_DEST" 2>/dev/null || true
    # Copiar todos los directorios
    [ -d "$SITES_AVAILABLE_SRC" ] && cp -rf "$SITES_AVAILABLE_SRC"/* "$SITES_AVAILABLE_DEST/" 2>/dev/null || true
    [ -d "$SITES_ENABLED_SRC" ] && cp -rf "$SITES_ENABLED_SRC"/* "$SITES_ENABLED_DEST/" 2>/dev/null || true
    [ -d "$CONF_AVAILABLE_SRC" ] && cp -rf "$CONF_AVAILABLE_SRC"/* "$CONF_AVAILABLE_DEST/" 2>/dev/null || true
    [ -d "$CONF_ENABLED_SRC" ] && cp -rf "$CONF_ENABLED_SRC"/* "$CONF_ENABLED_DEST/" 2>/dev/null || true
    [ -d "$MODS_AVAILABLE_SRC" ] && cp -rf "$MODS_AVAILABLE_SRC"/* "$MODS_AVAILABLE_DEST/" 2>/dev/null || true
    [ -d "$MODS_ENABLED_SRC" ] && cp -rf "$MODS_ENABLED_SRC"/* "$MODS_ENABLED_DEST/" 2>/dev/null || true
    
    # Eliminar archivos huérfanos en WSL (que no existen en el directorio local)
    cleanup_orphans() {
        local s_dir="$1"
        local d_dir="$2"
        [ -d "$s_dir" ] && [ -d "$d_dir" ] || return 0
        # Usar find con manejo seguro de errores
        find "$d_dir" -type f \( -name "*.conf" -o -name "*.load" \) 2>/dev/null | while IFS= read -r dest_file || [ -n "$dest_file" ]; do
            [ -z "$dest_file" ] && continue
            rel_path="${dest_file#$d_dir/}"
            src_file="$s_dir/$rel_path"
            # Si el archivo no existe en el origen, eliminarlo del destino
            if [ ! -f "$src_file" ] && [[ "$dest_file" =~ \.(conf|load)$ ]]; then
                rm -f "$dest_file" 2>/dev/null && log "🗑️  Archivo huérfano eliminado: $rel_path" "$YELLOW" || true
            fi
        done || true
    }
    cleanup_orphans "$SITES_AVAILABLE_SRC" "$SITES_AVAILABLE_DEST"
    cleanup_orphans "$SITES_ENABLED_SRC" "$SITES_ENABLED_DEST"
    cleanup_orphans "$CONF_AVAILABLE_SRC" "$CONF_AVAILABLE_DEST"
    cleanup_orphans "$CONF_ENABLED_SRC" "$CONF_ENABLED_DEST"
    cleanup_orphans "$MODS_AVAILABLE_SRC" "$MODS_AVAILABLE_DEST"
    cleanup_orphans "$MODS_ENABLED_SRC" "$MODS_ENABLED_DEST"
    
    # Habilitar automáticamente todos los archivos de dev/
    if [ -d "/etc/apache2/sites-available/dev" ]; then
        while IFS= read -r conf_file; do
            conf_name=$(basename "$conf_file")
            enabled_link="/etc/apache2/sites-enabled/$conf_name"
            
            # Si el symlink no existe, crearlo
            if [ ! -e "$enabled_link" ]; then
                ln -sf "../sites-available/dev/$conf_name" "$enabled_link" 2>/dev/null
                chown -h root:root "$enabled_link" 2>/dev/null
                log "✅ Habilitado automáticamente: dev/$conf_name" "$GREEN"
            fi
        done < <(find "/etc/apache2/sites-available/dev" -name "*.conf" -type f 2>/dev/null)
    fi
else
    # En Linux nativo usamos rsync (con --delete para eliminar archivos huérfanos)
    [ -f "$PORTS_CONF_SRC" ] && cp -f "$PORTS_CONF_SRC" "$PORTS_CONF_DEST" 2>/dev/null && chown root:root "$PORTS_CONF_DEST" 2>/dev/null && chmod 644 "$PORTS_CONF_DEST" 2>/dev/null || true
    [ -d "$SITES_AVAILABLE_SRC" ] && rsync -av --delete "$SITES_AVAILABLE_SRC/" "$SITES_AVAILABLE_DEST/" >> "$LOG_FILE" 2>&1
    [ -d "$SITES_ENABLED_SRC" ] && rsync -av --delete "$SITES_ENABLED_SRC/" "$SITES_ENABLED_DEST/" >> "$LOG_FILE" 2>&1
    [ -d "$CONF_AVAILABLE_SRC" ] && rsync -av --delete "$CONF_AVAILABLE_SRC/" "$CONF_AVAILABLE_DEST/" >> "$LOG_FILE" 2>&1
    [ -d "$CONF_ENABLED_SRC" ] && rsync -av --delete "$CONF_ENABLED_SRC/" "$CONF_ENABLED_DEST/" >> "$LOG_FILE" 2>&1
    [ -d "$MODS_AVAILABLE_SRC" ] && rsync -av --delete "$MODS_AVAILABLE_SRC/" "$MODS_AVAILABLE_DEST/" >> "$LOG_FILE" 2>&1
    [ -d "$MODS_ENABLED_SRC" ] && rsync -av --delete "$MODS_ENABLED_SRC/" "$MODS_ENABLED_DEST/" >> "$LOG_FILE" 2>&1
    
    # Habilitar automáticamente todos los archivos de dev/
    if [ -d "/etc/apache2/sites-available/dev" ]; then
        while IFS= read -r conf_file; do
            conf_name=$(basename "$conf_file")
            enabled_link="/etc/apache2/sites-enabled/$conf_name"
            
            # Si el symlink no existe, crearlo
            if [ ! -e "$enabled_link" ]; then
                ln -sf "../sites-available/dev/$conf_name" "$enabled_link" 2>/dev/null
                chown -h root:root "$enabled_link" 2>/dev/null
                log "✅ Habilitado automáticamente: dev/$conf_name" "$GREEN"
            fi
        done < <(find "/etc/apache2/sites-available/dev" -name "*.conf" -type f 2>/dev/null)
    fi
fi

# Sincronizar ports.conf también
[ -f "$PORTS_CONF_DEST" ] && chown root:root "$PORTS_CONF_DEST" 2>/dev/null && chmod 644 "$PORTS_CONF_DEST" 2>/dev/null || true

# Cambiar ownership de todos los archivos a root:root
for dir in "$SITES_AVAILABLE_DEST" "$SITES_ENABLED_DEST" "$CONF_AVAILABLE_DEST" "$CONF_ENABLED_DEST" "$MODS_AVAILABLE_DEST" "$MODS_ENABLED_DEST"; do
    [ -d "$dir" ] && find "$dir" -type f -exec chown root:root {} \; 2>/dev/null
    [ -d "$dir" ] && find "$dir" -type d -exec chown root:root {} \; 2>/dev/null
    [ -d "$dir" ] && find "$dir" -type f -exec chmod 644 {} \; 2>/dev/null
done

log "✅ Sincronización inicial completada (ports.conf + sites-available + sites-enabled + conf-available + conf-enabled + mods-available + mods-enabled) - permisos root:root" "$GREEN"

# Inicia hilo de recarga
monitor_reload &

# Monitoreo en tiempo real
log "👀 Escuchando cambios en:" "$YELLOW"
[ -f "$PORTS_CONF_SRC" ] && log "   - ports.conf: $PORTS_CONF_SRC" "$YELLOW"
[ -d "$SITES_AVAILABLE_SRC" ] && log "   - sites-available: $SITES_AVAILABLE_SRC" "$YELLOW"
[ -d "$SITES_ENABLED_SRC" ] && log "   - sites-enabled: $SITES_ENABLED_SRC" "$YELLOW"
[ -d "$CONF_AVAILABLE_SRC" ] && log "   - conf-available: $CONF_AVAILABLE_SRC" "$YELLOW"
[ -d "$CONF_ENABLED_SRC" ] && log "   - conf-enabled: $CONF_ENABLED_SRC" "$YELLOW"
[ -d "$MODS_AVAILABLE_SRC" ] && log "   - mods-available: $MODS_AVAILABLE_SRC" "$YELLOW"
[ -d "$MODS_ENABLED_SRC" ] && log "   - mods-enabled: $MODS_ENABLED_SRC" "$YELLOW"

# Detectar si estamos en WSL
if grep -qi microsoft /proc/version 2>/dev/null; then
    log "⚠️  WSL detectado - inotify NO funciona en /mnt/c/" "$YELLOW"
    log "🔧 Usando polling optimizado (solo sincroniza archivos modificados)" "$BLUE"
    
    # Array asociativo para guardar hash de cada archivo
    declare -A FILE_HASHES
    
    # Generar hashes iniciales de todos los directorios y ports.conf
    # Incluir archivos regulares Y symlinks
    [ -f "$PORTS_CONF_SRC" ] && hash=$(md5sum "$PORTS_CONF_SRC" 2>/dev/null | awk '{print $1}') && FILE_HASHES["$PORTS_CONF_SRC"]="$hash" || true
    for src_dir in "$SITES_AVAILABLE_SRC" "$SITES_ENABLED_SRC" "$CONF_AVAILABLE_SRC" "$CONF_ENABLED_SRC" "$MODS_AVAILABLE_SRC" "$MODS_ENABLED_SRC"; do
        [ -d "$src_dir" ] || continue
        while IFS= read -r file; do
            # Para symlinks, usar el path del symlink como hash (cambia cuando cambia el destino)
            if [ -L "$file" ]; then
                hash=$(readlink -f "$file" 2>/dev/null || readlink "$file" 2>/dev/null || echo "$file")
            else
                hash=$(md5sum "$file" 2>/dev/null | awk '{print $1}')
            fi
            FILE_HASHES["$file"]="$hash"
        done < <(find "$src_dir" \( -type f -o -type l \) \( -name "*.conf" -o -name "*.load" \) 2>/dev/null)
    done
    
    # Loop de polling optimizado
    while true; do
        sleep 3
        
        # Revisar ports.conf primero
        if [ -f "$PORTS_CONF_SRC" ]; then
            current_hash=$(md5sum "$PORTS_CONF_SRC" 2>/dev/null | awk '{print $1}')
            previous_hash="${FILE_HASHES[$PORTS_CONF_SRC]}"
            if [ "$current_hash" != "$previous_hash" ]; then
                sync_file "$PORTS_CONF_SRC"
                FILE_HASHES["$PORTS_CONF_SRC"]="$current_hash"
            fi
        fi
        
        # Revisar archivos en todos los directorios (incluyendo symlinks)
        for src_dir in "$SITES_AVAILABLE_SRC" "$SITES_ENABLED_SRC" "$CONF_AVAILABLE_SRC" "$CONF_ENABLED_SRC" "$MODS_AVAILABLE_SRC" "$MODS_ENABLED_SRC"; do
            [ -d "$src_dir" ] || continue
            
            # Obtener lista actual de archivos (incluyendo symlinks)
            declare -A CURRENT_FILES
            while IFS= read -r file; do
                CURRENT_FILES["$file"]=1
                # Para symlinks, usar el path del symlink como hash
                if [ -L "$file" ]; then
                    current_hash=$(readlink -f "$file" 2>/dev/null || readlink "$file" 2>/dev/null || echo "$file")
                else
                    current_hash=$(md5sum "$file" 2>/dev/null | awk '{print $1}')
                fi
                previous_hash="${FILE_HASHES[$file]}"
                
                # Si el hash cambió o es un archivo nuevo, sincronizar
                if [ "$current_hash" != "$previous_hash" ]; then
                    sync_file "$file"
                    FILE_HASHES["$file"]="$current_hash"
                fi
            done < <(find "$src_dir" \( -type f -o -type l \) \( -name "*.conf" -o -name "*.load" \) 2>/dev/null)
            
            # Detectar archivos eliminados (estaban en FILE_HASHES pero no en CURRENT_FILES)
            for file in "${!FILE_HASHES[@]}"; do
                if [[ "$file" == "$src_dir"/* ]] && [ -z "${CURRENT_FILES[$file]}" ]; then
                    delete_file "$file"
                    unset FILE_HASHES["$file"]
                fi
            done
        done
        
        # Habilitar automáticamente todos los archivos de dev/ (cada ciclo de polling)
        if [ -d "/etc/apache2/sites-available/dev" ]; then
            while IFS= read -r conf_file; do
                conf_name=$(basename "$conf_file")
                enabled_link="/etc/apache2/sites-enabled/$conf_name"
                
                # Si el symlink no existe, crearlo
                if [ ! -e "$enabled_link" ]; then
                    ln -sf "../sites-available/dev/$conf_name" "$enabled_link" 2>/dev/null
                    chown -h root:root "$enabled_link" 2>/dev/null
                    log "✅ Habilitado automáticamente: dev/$conf_name" "$GREEN"
                    schedule_reload
                fi
            done < <(find "/etc/apache2/sites-available/dev" -name "*.conf" -type f 2>/dev/null)
        fi
    done
else
    # Linux nativo - usar inotify (más eficiente) para todos los directorios y ports.conf
    log "🔧 Usando inotify - detección instantánea" "$GREEN"
    WATCH_DIRS=()
    [ -d "$SITES_AVAILABLE_SRC" ] && WATCH_DIRS+=("$SITES_AVAILABLE_SRC")
    [ -d "$SITES_ENABLED_SRC" ] && WATCH_DIRS+=("$SITES_ENABLED_SRC")
    [ -d "$CONF_AVAILABLE_SRC" ] && WATCH_DIRS+=("$CONF_AVAILABLE_SRC")
    [ -d "$CONF_ENABLED_SRC" ] && WATCH_DIRS+=("$CONF_ENABLED_SRC")
    [ -d "$MODS_AVAILABLE_SRC" ] && WATCH_DIRS+=("$MODS_AVAILABLE_SRC")
    [ -d "$MODS_ENABLED_SRC" ] && WATCH_DIRS+=("$MODS_ENABLED_SRC")
    # Monitorear el directorio padre para detectar cambios en ports.conf
    [ -d "$CONFIG_DIR" ] && WATCH_DIRS+=("$CONFIG_DIR")
    
    inotifywait -m -r -e create,modify,delete,move,close_write "${WATCH_DIRS[@]}" --format '%w%f %e' |
    while read -r file event; do
        # Si es ports.conf, sincronizarlo
        if [[ "$file" == "$PORTS_CONF_SRC" ]]; then
            case "$event" in
                *CREATE*|*MODIFY*|*CLOSE_WRITE*|*MOVED_TO*)
                    sync_file "$file"
                    ;;
                *DELETE*|*MOVED_FROM*)
                    # Si se elimina ports.conf en origen, no hacemos nada (dejar el del sistema)
                    ;;
            esac
        else
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
        fi
    done
fi

