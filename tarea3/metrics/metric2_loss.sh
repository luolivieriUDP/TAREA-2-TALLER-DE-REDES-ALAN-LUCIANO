#!/usr/bin/env bash
# ============================================================================
# metric2_loss.sh  -  MÉTRICA 2: PÉRDIDA DE PAQUETES (loss) con tc netem
# Tarea 3 - Taller de Redes y Servicios (UDP)
# ----------------------------------------------------------------------------
# Aplica pérdida de paquetes artificial a la interfaz del cliente con
# `tc qdisc netem loss` y mide cómo varía el throughput del enlace PostgreSQL.
# Genera metric2_results.csv.
#
# REQUISITO: cap_add NET_ADMIN (o usar NETEM_CONTAINER=scapy_mitm).
#
#   bash metric2_loss.sh
# ============================================================================
set -u

# ----------------------- CONFIGURACIÓN (editar aquí) ------------------------
CLIENT_CONTAINER="${CLIENT_CONTAINER:-psql-cliente}"
SERVER_CONTAINER="${SERVER_CONTAINER:-psql-servidor}"
NETEM_CONTAINER="${NETEM_CONTAINER:-$CLIENT_CONTAINER}"
SERVER_HOST="${SERVER_HOST:-servidor}"
NET_IFACE="${NET_IFACE:-eth0}"
PG_USER="${PG_USER:-taller}"
PG_PASSWORD="${PG_PASSWORD:-tallerpass}"
PG_DB="${PG_DB:-tallerdb}"
N_QUERIES="${N_QUERIES:-100}"
CONNECT_TIMEOUT="${CONNECT_TIMEOUT:-10}"
OUT_CSV="${OUT_CSV:-$(dirname "$0")/metric2_results.csv}"
LOSSES=(0 1 5 10 20 30 50)
# ----------------------------------------------------------------------------

echo "loss_pct,throughput_ops_sec,elapsed_ms,status" > "$OUT_CSV"
echo "=== MÉTRICA 2: PÉRDIDA DE PAQUETES (tc netem loss) ==="
echo "Aplicando tc en: $NETEM_CONTAINER ($NET_IFACE) | Servidor: $SERVER_HOST"

build_queries() {
    yes "SELECT 1;" 2>/dev/null | head -n "$N_QUERIES"
}

for loss in "${LOSSES[@]}"; do
    docker exec -u root "$NETEM_CONTAINER" tc qdisc del dev "$NET_IFACE" root 2>/dev/null || true

    if [ "$loss" -gt 0 ]; then
        docker exec -u root "$NETEM_CONTAINER" \
            tc qdisc add dev "$NET_IFACE" root netem loss "${loss}%"
    fi

    start=$(date +%s.%N)
    out=$(build_queries | docker exec -i \
            -e PGPASSWORD="$PG_PASSWORD" -e PGCONNECT_TIMEOUT="$CONNECT_TIMEOUT" \
            "$CLIENT_CONTAINER" \
            psql -h "$SERVER_HOST" -U "$PG_USER" -d "$PG_DB" -qtA 2>&1)
    rc=$?
    end=$(date +%s.%N)

    elapsed_ms=$(awk "BEGIN{printf \"%.1f\", ($end-$start)*1000}")

    if [ $rc -ne 0 ] || echo "$out" | grep -qiE "error|fatal|timeout|could not connect|terminating"; then
        status="error"
        throughput="0"
    else
        status="ok"
        throughput=$(awk "BEGIN{printf \"%.2f\", $N_QUERIES/(($end-$start))}")
    fi

    echo "  loss=${loss}%  elapsed=${elapsed_ms}ms  throughput=${throughput} ops/s  [$status]"
    echo "${loss},${throughput},${elapsed_ms},${status}" >> "$OUT_CSV"

    docker exec -u root "$NETEM_CONTAINER" tc qdisc del dev "$NET_IFACE" root 2>/dev/null || true
    sleep 2
done

echo "=== Listo. Resultados en $OUT_CSV ==="
cat "$OUT_CSV"
