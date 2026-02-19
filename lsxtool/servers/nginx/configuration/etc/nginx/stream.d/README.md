# Stream (TCP) – Nginx

Configuraciones `stream` para proxy TCP (PostgreSQL, etc.).  
Para que se carguen, el `nginx.conf` principal debe incluir:

```nginx
stream {
    include /etc/nginx/stream.d/*.conf;
}
```

## Lunarsystemx dev

- **pg13-core.dev.lunarsystemx.com** → `lunarsystemx-dev-pg13-core.conf`  
  Escucha en `15433`, proxy a `192.168.20.234:5433` (PostgreSQL 13).  
  Traefik entrypoint `postgres-dev` (:5433) envía a `localhost:15433`.
