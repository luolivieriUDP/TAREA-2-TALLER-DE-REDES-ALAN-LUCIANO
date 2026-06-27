#!/usr/bin/env bash
# ============================================================
# entrypoint.sh - Servidor PostgreSQL (Tarea 2, recreado)
# Inicializa el cluster, fija autenticación SCRAM-SHA-256, crea el
# rol/base/tabla de prueba y deja a postgres escuchando en 5432.
# ============================================================
set -euo pipefail

PG_BIN="/usr/lib/postgresql/${PG_MAJOR}/bin"
PG_USER="${POSTGRES_USER:-taller}"
PG_PASSWORD="${POSTGRES_PASSWORD:-tallerpass}"
PG_DB="${POSTGRES_DB:-tallerdb}"

# Inicializar el cluster solo la primera vez
if [ ! -s "${PGDATA}/PG_VERSION" ]; then
    echo "[entrypoint] Inicializando cluster en ${PGDATA} con SCRAM-SHA-256"
    # Limpiar restos de un initdb previo fallido (si los hubiera)
    rm -rf "${PGDATA:?}"/* 2>/dev/null || true
    # initdb con SCRAM exige contraseña para el superusuario -> pwfile temporal
    PWFILE="$(mktemp)"
    printf '%s' "${PG_PASSWORD}" > "${PWFILE}"
    "${PG_BIN}/initdb" -D "${PGDATA}" \
        --auth-host=scram-sha-256 \
        --auth-local=scram-sha-256 \
        --username=postgres \
        --pwfile="${PWFILE}" \
        --encoding=UTF8 --locale=en_US.UTF-8 >/dev/null
    rm -f "${PWFILE}"

    # Escuchar en todas las interfaces y exigir SCRAM por TCP
    echo "listen_addresses = '*'"               >> "${PGDATA}/postgresql.conf"
    echo "password_encryption = scram-sha-256"  >> "${PGDATA}/postgresql.conf"
    echo "host all all 0.0.0.0/0 scram-sha-256" >> "${PGDATA}/pg_hba.conf"
    echo "host all all ::/0      scram-sha-256" >> "${PGDATA}/pg_hba.conf"

    # Arranque temporal para crear rol, base y tabla.
    # initdb dejó al superusuario postgres con SCRAM; los psql de setup se
    # conectan por socket local, así que necesitan la contraseña.
    export PGPASSWORD="${PG_PASSWORD}"
    "${PG_BIN}/pg_ctl" -D "${PGDATA}" -o "-c listen_addresses='localhost'" -w start

    "${PG_BIN}/psql" -v ON_ERROR_STOP=1 --username postgres --dbname postgres <<-SQL
        CREATE ROLE ${PG_USER} LOGIN PASSWORD '${PG_PASSWORD}' SUPERUSER;
        CREATE DATABASE ${PG_DB} OWNER ${PG_USER};
SQL

    "${PG_BIN}/psql" -v ON_ERROR_STOP=1 --username postgres --dbname "${PG_DB}" \
        -f /docker-init/01-esquema.sql

    "${PG_BIN}/pg_ctl" -D "${PGDATA}" -m fast -w stop
    echo "[entrypoint] Inicialización completa."
fi

echo "[entrypoint] Arrancando postgres en el puerto 5432..."
exec "${PG_BIN}/postgres" -D "${PGDATA}"
