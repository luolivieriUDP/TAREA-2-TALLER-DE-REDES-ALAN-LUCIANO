#!/usr/bin/env bash
# ============================================================================
# metric1_latency.sh  -  MÉTRICA 1: LATENCIA (delay) con tc netem
# Tarea 3 - Taller de Redes y Servicios (UDP)
# ----------------------------------------------------------------------------
# Aplica latencia artificial a la interfaz de red del cliente con
# `tc qdisc netem delay` y mide cómo varía el throughput (consultas/seg) del
# enlace PostgreSQL. Genera metric1_results.csv.
#
# REQUISITO: el contenedor donde se aplica tc debe tener cap_add: NET_ADMIN.
# Si el cliente no lo tiene, exporte NETEM_CONTAINER=scapy_mitm (privileged).
#
#   bash metric1_latency.sh
# ============================================================================
set -u

# ----------------------- CONFIGURACIÓN (editar aquí) ------------------------
CLIENT_CONTAINER="${CLIENT_CONTAINER:-psql-cliente}"
SERVER_CONTAINER="${SERVER_CONTAINER:-psql-servidor}"
NETEM_CONTAINER="${NETEM_CONTAINER:-$CLIENT_CONTAINER}"  # dónde se aplica tc
SERVER_HOST="${SERVER_HOST:-servidor}"                   # alias en redpsql
NET_IFACE="${NET_IFACE:-eth0}"
PG_USER="${PG_USER:-taller}"
PG_PASSWORD="${PG_PASSWORD:-tallerpass}"
PG_DB="${PG_DB:-tallerdb}"
N_QUERIES="${N_QUERIES:-100}"
OUT_CSV="${OUT_CSV:-$(dirname "$0")/metric1_results.csv}"
DELAYS=(0 10 50 100 200 300 500 1000)
# ----------------------------------------------------------------------------

echo "delay_ms,throughput_ops_sec,elapsed_ms,status" > "$OUT_CSV"
echo "=== MÉTRICA 1: LATENCIA (tc netem delay) ==="
echo "Aplicando tc en: $NETEM_CONTAINER ($NET_IFACE) | Servidor: $SERVER_HOST"

# Genera N_QUERIES sentencias 'SELECT 1;' separadas -> N_QUERIES round-trips.
# (Un DO loop server-side incurriría en UN solo RTT y no mostraría la latencia.)
build_queries() {
    yes "SELECT 1;" 2>/dev/null | head -n "$N_QUERIES"
}

for delay in "${DELAYS[@]}"; do
    # 1. Limpiar qdisc previo
    docker exec -u root "$NETEM_CONTAINER" tc qdisc del dev "$NET_IFACE" root 2>/dev/null || true

    # 2. Aplicar la latencia (delay 0 = sin qdisc)
    if [ "$delay" -gt 0 ]; then
        docker exec -u root "$NETEM_CONTAINER" \
            tc qdisc add dev "$NET_IFACE" root netem delay "${delay}ms"
    fi

    # 3. Medir: N_QUERIES round-trips en una sesión psql
    start=$(date +%s.%N)
    out=$(build_queries | docker exec -i \
            -e PGPASSWORD="$PG_PASSWORD" "$CLIENT_CONTAINER" \
            psql -h "$SERVER_HOST" -U "$PG_USER" -d "$PG_DB" -qtA 2>&1)
    rc=$?
    end=$(date +%s.%N)

    elapsed_ms=$(awk "BEGIN{printf \"%.1f\", ($end-$start)*1000}")

    # 4. Clasificar
    if [ $rc -ne 0 ] || echo "$out" | grep -qiE "error|fatal|timeout|could not connect"; then
        status="error"
        throughput="0"
    else
        status="ok"
        throughput=$(awk "BEGIN{printf \"%.2f\", $N_QUERIES/(($end-$start))}")
    fi

    echo "  delay=${delay}ms  elapsed=${elapsed_ms}ms  throughput=${throughput} ops/s  [$status]"
    echo "${delay},${throughput},${elapsed_ms},${status}" >> "$OUT_CSV"

    # 5. Limpiar y pausar
    docker exec -u root "$NETEM_CONTAINER" tc qdisc del dev "$NET_IFACE" root 2>/dev/null || true
    sleep 2
done

echo "=== Listo. Resultados en $OUT_CSV ==="
cat "$OUT_CSV"
