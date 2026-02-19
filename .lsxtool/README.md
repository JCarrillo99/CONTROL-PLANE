# Core: .lsxtool

Estructura **core** de configuración de lsxtool. Todo lo que está “dado de alta” se basa en esto.

## Estructura

```
.lsxtool/
├── catalog/                    # Catálogo (definiciones disponibles)
│   ├── providers.yaml         # Providers que se pueden dar de alta
│   ├── capabilities/          # Capacidades por tipo (servers, security, …)
│   │   ├── servers.yaml
│   │   └── security.yaml
│   └── services/
│       └── servers/            # Servicios por tipo
│           ├── web/            # nginx, traefik, apache
│           └── database/       # postgresql, mysql
├── config/                     # Configuración por provider (uno por archivo)
│   └── {provider_id}.yaml     # provider + capabilities (servers_web, …)
└── providers/                  # Datos por provider (servidores, sitios, etc.)
    └── {provider_id}/
        └── servers/
            └── {service}/{env}/*.yml
```

## Flujo

1. **Catálogo** define qué puede existir (providers, capacidades, servicios).
2. **`lsxtool providers add`** da de alta un provider: crea `config/{id}.yaml` y `providers/{id}/`.
3. **`lsxtool servers add`** crea un servidor bajo un provider ya configurado (usa `config/{id}.yaml` y catálogo de servicios).
4. **`lsxtool servers sync`** sincroniza solo servidores dados de alta (según YAML en `providers/`).

Nada es opcional por defecto: solo existe lo que se da de alta desde el catálogo.
