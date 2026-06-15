# =====================================================================
# Imagen del SERVIDOR PostgreSQL — CONSTRUIDA, no importada.
# Base Debian + instalación de PostgreSQL desde el repositorio oficial PGDG
# (apt.postgresql.org). Incluye tcpdump para capturar el tráfico del protocolo.
# Construir (contexto = carpeta docker/):
#   docker build -t tarea2/psql-servidor -f servidor/Dockerfile .
# =====================================================================
FROM debian:bookworm-slim

ENV PG_MAJOR=17 \
    PGDATA=/var/lib/postgresql/data \
    LANG=C.UTF-8
# Las credenciales (taller / redes2025 / tallerdb) las define entrypoint.sh por defecto.

# Repositorio oficial PGDG + servidor PostgreSQL + tcpdump
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates curl gnupg tcpdump procps; \
    install -d /usr/share/postgresql-common/pgdg; \
    curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
        -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc; \
    echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends "postgresql-${PG_MAJOR}"; \
    rm -rf /var/lib/apt/lists/*; \
    mkdir -p "$PGDATA" /var/run/postgresql; \
    chown -R postgres:postgres "$PGDATA" /var/run/postgresql

ENV PATH="/usr/lib/postgresql/${PG_MAJOR}/bin:${PATH}"

# Esquema inicial y arranque
COPY init/01-esquema.sql /docker-init/01-esquema.sql
COPY servidor/entrypoint.sh /usr/local/bin/entrypoint.sh
# Normaliza finales de línea (por si se editó en Windows) y da permisos
RUN sed -i 's/\r$//' /usr/local/bin/entrypoint.sh && chmod +x /usr/local/bin/entrypoint.sh

EXPOSE 5432
USER postgres
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
