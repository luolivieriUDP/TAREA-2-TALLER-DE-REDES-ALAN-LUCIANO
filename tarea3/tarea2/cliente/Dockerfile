# ============================================================
# Cliente psql (recreado fielmente desde el informe Tarea 2)
# Imagen: tarea2/psql-cliente
# Instala postgresql-client-17 (binario psql) desde PGDG.
# Se mantiene en espera; desde él se abren las sesiones al servidor.
# Incluye NET_ADMIN-friendly tooling (iproute2) para tc netem.
# ============================================================
FROM debian:bookworm-slim

ENV PG_MAJOR=17 \
    DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        ca-certificates curl gnupg procps iproute2 iputils-ping \
 && install -d /usr/share/postgresql-common/pgdg \
 && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
        -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
 && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends postgresql-client-$PG_MAJOR \
 && rm -rf /var/lib/apt/lists/*

# Mantener el contenedor vivo a la espera de sesiones interactivas
CMD ["sleep", "infinity"]
