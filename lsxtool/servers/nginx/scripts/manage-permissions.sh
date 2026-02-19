#!/bin/bash

# Script para gestionar permisos del grupo lunarsystemx
# LSX - 2025

GROUP="lunarsystemx"
DIR="/var/www/lunarsystemx/00-default"

# Crear grupo si no existe
if ! getent group "$GROUP" > /dev/null; then
    echo "El grupo $GROUP no existe, creando..."
    groupadd "$GROUP"
fi

# Preguntar acción
echo "¿Qué deseas hacer?"
echo "1) Agregar usuario al grupo"
echo "2) Quitar usuario del grupo"
read -rp "Selecciona opción [1/2]: " ACTION

# Preguntar usuario
read -rp "Nombre del usuario: " USER

case "$ACTION" in
    1)
        usermod -aG "$GROUP" "$USER"
        echo "Usuario $USER agregado al grupo $GROUP."
        ;;
    2)
        gpasswd -d "$USER" "$GROUP"
        echo "Usuario $USER eliminado del grupo $GROUP."
        ;;
    *)
        echo "Opción inválida"
        exit 1
        ;;
esac

# Ajustar permisos del directorio
echo "Ajustando permisos en $DIR..."
chown -R root:"$GROUP" "$DIR"
chmod -R 775 "$DIR"
chmod g+s "$DIR"  # que nuevos archivos hereden grupo

echo "Permisos aplicados. Cierra sesión y vuelve a entrar para que los cambios surtan efecto."
