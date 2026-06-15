# =====================================================================
# Imagen del CLIENTE psql — CONSTRUIDA, no importada.
# Base Debian + cliente PostgreSQL desde el repositorio oficial PGDG.
# Construir (contexto = carpeta docker/):
#   docker build -t tarea2/psql-cliente -f cliente/Dockerfile .
# =====================================================================
FROM debian:bookworm-slim

ENV PG_MAJOR=17 \
    LANG=C.UTF-8

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates curl gnupg; \
    install -d /usr/share/postgresql-common/pgdg; \
    curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
        -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc; \
    echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends "postgresql-client-${PG_MAJOR}"; \
    rm -rf /var/lib/apt/lists/*

ENV PATH="/usr/lib/postgresql/${PG_MAJOR}/bin:${PATH}"

# Se mantiene vivo para abrir sesiones con:
#   docker exec -it psql-cliente psql -h servidor -U taller -d tallerdb
CMD ["sleep", "infinity"]
// ==========================================================