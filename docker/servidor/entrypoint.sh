#!/bin/bash
# Arranque del servidor PostgreSQL construido desde cero.
# En el primer arranque inicializa el cluster, crea el rol, la base y el esquema;
# en arranques posteriores reutiliza los datos.
set -e

: "${PGDATA:=/var/lib/postgresql/data}"
: "${POSTGRES_USER:=taller}"
: "${POSTGRES_PASSWORD:=redes2025}"
: "${POSTGRES_DB:=tallerdb}"
SOCK=/var/run/postgresql

if [ ! -s "$PGDATA/PG_VERSION" ]; then
    echo "[entrypoint] Inicializando cluster nuevo en $PGDATA"
    initdb -D "$PGDATA" -E UTF8 --auth-host=scram-sha-256 --auth-local=trust >/dev/null

    {
        echo "listen_addresses = '*'"
        echo "password_encryption = scram-sha-256"
        echo "unix_socket_directories = '$SOCK'"
    } >> "$PGDATA/postgresql.conf"
    echo "host all all 0.0.0.0/0 scram-sha-256" >> "$PGDATA/pg_hba.conf"

    echo "[entrypoint] Creando rol, base y esquema inicial"
    pg_ctl -D "$PGDATA" -o "-c listen_addresses='' -c unix_socket_directories='$SOCK'" -w start
    psql -h "$SOCK" -v ON_ERROR_STOP=1 --username postgres --dbname postgres <<EOSQL
CREATE ROLE "$POSTGRES_USER" LOGIN PASSWORD '$POSTGRES_PASSWORD';
CREATE DATABASE "$POSTGRES_DB" OWNER "$POSTGRES_USER";
EOSQL
    psql -h "$SOCK" -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -f /docker-init/01-esquema.sql
    pg_ctl -D "$PGDATA" -m fast -w stop
    echo "[entrypoint] Inicialización completa"
fi

echo "[entrypoint] Arrancando PostgreSQL en primer plano"
exec postgres -D "$PGDATA"
