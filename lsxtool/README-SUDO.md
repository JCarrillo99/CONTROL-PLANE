# Ejecutar lsxtool con sudo

Cuando necesites ejecutar comandos que requieren permisos de root (como modificar `/etc/hosts` o recargar servicios), usa una de estas opciones:

## Opción 1: Usar sudo -E (preserva el entorno)

```bash
sudo -E python3 lsxtool/cli.py servers sites info <domain>
```

## Opción 2: Usar el Python del venv directamente

```bash
sudo lsxtool/venv/bin/python3 lsxtool/cli.py servers sites info <domain>
```

## Opción 3: Activar el venv antes de usar sudo

```bash
source lsxtool/venv/bin/activate
sudo python3 lsxtool/cli.py servers sites info <domain>
```

## Nota sobre /etc/hosts

Si no tienes permisos de root, el sistema mostrará instrucciones para agregar manualmente el dominio a `/etc/hosts`:

```bash
echo '127.0.0.1    dominio.com' | sudo tee -a /etc/hosts
```
