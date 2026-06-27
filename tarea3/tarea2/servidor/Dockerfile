# ============================================================
# Servidor PostgreSQL 17 (recreado fielmente desde el informe Tarea 2)
# Imagen: tarea2/psql-servidor
# Instala PostgreSQL desde el repositorio oficial PGDG + tcpdump.
# ============================================================
FROM debian:bookworm-slim

ENV PG_MAJOR=17 \
    PGDATA=/var/lib/postgresql/data \
    DEBIAN_FRONTEND=noninteractive

# Repositorio oficial PGDG + servidor PostgreSQL + tcpdump
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        ca-certificates curl gnupg tcpdump procps locales \
 && install -d /usr/share/postgresql-common/pgdg \
 && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
        -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
 && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends postgresql-$PG_MAJOR \
 && sed -i 's/^# *en_US.UTF-8/en_US.UTF-8/' /etc/locale.gen && locale-gen \
 && rm -rf /var/lib/apt/lists/*

# Esquema inicial (tabla routers con 4 filas) y script de arranque
COPY init/01-esquema.sql /docker-init/01-esquema.sql
COPY servidor/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh \
 && chown -R postgres:postgres /docker-init /var/lib/postgresql

EXPOSE 5432
USER postgres
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
