#!/bin/bash
# =====================================================
# Script: set-nginx-editor.sh
# Autor: LSX
# Propósito: Gestionar acceso automático a nginx
# =====================================================

# Detectar directorio del script y calcular rutas
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_PROJECT_DIR="$SCRIPT_DIR/configuration"

GROUP_NAME="nginx-editors"
TARGET_DIR="/etc/nginx"

echo "=============================================="
echo "  GESTIÓN AUTOMÁTICA DE ACCESO A NGINX"
echo "=============================================="
echo "📂 Sistema: $TARGET_DIR"
echo "📂 Proyecto: $LOCAL_PROJECT_DIR"
echo

# Preguntar acción
read -rp "¿Qué deseas hacer? [A]gregar / [E]liminar usuario del grupo $GROUP_NAME: " ACTION
ACTION=$(echo "$ACTION" | tr '[:upper:]' '[:lower:]') # pasar a minúscula

# Validar acción
if [[ "$ACTION" != "a" && "$ACTION" != "e" ]]; then
    echo "❌ Opción no válida. Usa 'a' para agregar o 'e' para eliminar."
    exit 1
fi

# Preguntar usuario
read -rp "Ingresa el nombre del usuario (Enter para usar '$USER'): " USER_NAME
USER_NAME=${USER_NAME:-$USER}

# Crear grupo si no existe
if ! getent group "$GROUP_NAME" >/dev/null; then
    echo "→ El grupo $GROUP_NAME no existe. Creándolo..."
    sudo groupadd "$GROUP_NAME"
fi

# Si es agregar
if [[ "$ACTION" == "a" ]]; then
    echo "→ Otorgando permisos al grupo sobre $TARGET_DIR"
    sudo chgrp -R "$GROUP_NAME" "$TARGET_DIR"
    sudo chmod -R g+w "$TARGET_DIR"

    echo "→ Otorgando permisos al grupo sobre $LOCAL_PROJECT_DIR"
    sudo chgrp -R "$GROUP_NAME" "$LOCAL_PROJECT_DIR"
    sudo chmod -R g+w "$LOCAL_PROJECT_DIR"
    
    echo "→ Cambiando propietario de archivos .conf a $USER_NAME..."
    sudo find "$LOCAL_PROJECT_DIR" -type f -name "*.conf" -exec chown "$USER_NAME:$GROUP_NAME" {} \;
    
    echo "→ Haciendo $GROUP_NAME grupo primario de $USER_NAME..."
    sudo usermod -g "$GROUP_NAME" "$USER_NAME"

    echo
    echo "✅ Usuario '$USER_NAME' ahora tiene '$GROUP_NAME' como grupo primario."
    echo "✅ Permisos otorgados en sistema y proyecto local."
    echo "✅ VS Code debería funcionar automáticamente."
    echo "🔁 Reinicia VS Code o cierra sesión para aplicar completamente."
    echo
    echo "💡 IMPORTANTE: Con el sistema de sincronización automática:"
    echo "   - Edita los archivos en: $LOCAL_PROJECT_DIR/etc/nginx/conf.d/"
    echo "   - Se copiarán automáticamente a: $TARGET_DIR/conf.d/"
    echo "   - Nginx se recargará automáticamente si la config es válida"
    echo "   - Para probar config: sudo nginx -t"
    echo "   - Para recargar manual: sudo nginx -s reload"

# Si es eliminar
else
    echo "→ Eliminando usuario '$USER_NAME' del grupo '$GROUP_NAME'..."
    sudo gpasswd -d "$USER_NAME" "$GROUP_NAME"

    echo "→ Revirtiendo grupo primario a grupo original..."
    sudo usermod -g "$USER_NAME" "$USER_NAME"

    echo "→ Revirtiendo propietario en $LOCAL_PROJECT_DIR a root..."
    sudo chown -R root:root "$LOCAL_PROJECT_DIR"
    sudo chmod -R g-w "$LOCAL_PROJECT_DIR"
    
    echo "→ Verificando cambio de propietario en archivos .conf..."
    sudo find "$LOCAL_PROJECT_DIR" -type f -name "*.conf" -exec chown root:root {} \; 2>/dev/null || true
    sudo find "$LOCAL_PROJECT_DIR" -type f -name "*.conf" -exec chmod 644 {} \; 2>/dev/null || true

    echo
    echo "✅ Usuario '$USER_NAME' eliminado del grupo '$GROUP_NAME'."
    echo "✅ Grupo primario revertido a '$USER_NAME'."
    echo "✅ Propietario revertido a root en proyecto local."
    echo "⚠️ Los permisos del grupo en $TARGET_DIR permanecen activos."
    echo "   Si deseas revertirlos completamente, ejecuta:"
    echo "   sudo chmod -R g-w $TARGET_DIR"
fi

echo
echo ">>> Estado actual:"
echo "📂 Sistema ($TARGET_DIR):"
ls -ld "$TARGET_DIR"
echo "📂 Proyecto ($LOCAL_PROJECT_DIR):"
ls -ld "$LOCAL_PROJECT_DIR"
echo "👤 Grupos del usuario $USER_NAME:"
groups "$USER_NAME"
echo "🎯 Grupo primario actual:"
id -gn "$USER_NAME"
