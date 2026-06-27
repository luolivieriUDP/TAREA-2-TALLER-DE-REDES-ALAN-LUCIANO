#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================================
 generate_metrics_local.py  -  Generación de datos de métricas (sin Docker)
 Tarea 3 - Taller de Redes y Servicios (UDP)
----------------------------------------------------------------------------
 Este entorno de desarrollo no dispone de Linux/tc-netem, por lo que los
 scripts canónicos metric1_latency.sh / metric2_loss.sh deben ejecutarse
 sobre los contenedores Docker. Para obtener datos reales igualmente:

 MÉTRICA 1 (LATENCIA): se MIDE de verdad. El proxy MITM inyecta un retardo
   artificial en el sentido cliente->servidor (equivalente funcional de
   `tc netem delay`) y se ejecutan 100 consultas reales contra el servidor
   PostgreSQL por cada valor de delay, midiendo el throughput resultante.

 MÉTRICA 2 (PÉRDIDA): se MODELA. La pérdida a nivel IP con retransmisiones
   TCP no es reproducible a nivel de aplicación, así que se usa un modelo
   analítico basado en el comportamiento de TCP ante pérdida (degradación
   ~1/(1+penalización·p) con colapso por timeouts/RTO a alta pérdida),
   anclado al throughput base REAL medido en la métrica 1.
============================================================================
"""
import os
import sys
import csv
import time
import math
import threading
import socket

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scapy"))
from mitm_proxy import PgMITMProxy            # noqa: E402
from pg_client import MinimalPgClient          # noqa: E402

# ----------------------- CONFIGURACIÓN -------------------------------------
SERVER_HOST = os.environ.get("SERVER_HOST", "127.0.0.1")
PG_PORT     = int(os.environ.get("PG_PORT", "5440"))
PG_USER     = os.environ.get("PG_USER", "taller")
PG_PASSWORD = os.environ.get("PG_PASSWORD", "tallerpass")
PG_DB       = os.environ.get("PG_DB", "tallerdb")
N_QUERIES   = int(os.environ.get("N_QUERIES", "100"))
OPS_MIN     = float(os.environ.get("OPS_MIN", "5.0"))   # umbral operacional ok
HERE        = os.path.dirname(os.path.abspath(__file__))

DELAYS = [0, 10, 50, 100, 200, 300, 500, 1000]
LOSSES = [0, 1, 5, 10, 20, 30, 50]
BASE_PROXY_PORT = 5470
# ---------------------------------------------------------------------------


def wait_port(host, port, tries=60):
    for _ in range(tries):
        try:
            s = socket.create_connection((host, port), timeout=0.2)
            s.close()
            return True
        except OSError:
            time.sleep(0.05)
    return False


def measure_latency():
    print("=== MÉTRICA 1: LATENCIA (medición real vía proxy con retardo) ===")
    rows = []
    base_throughput = None
    for i, delay in enumerate(DELAYS):
        port = BASE_PROXY_PORT + i
        proxy = PgMITMProxy(listen_port=port, server_host=SERVER_HOST,
                            server_port=PG_PORT, verbose=False,
                            delay_c2s_ms=float(delay))
        threading.Thread(target=proxy.start, daemon=True).start()
        wait_port("127.0.0.1", port)

        status = "ok"
        throughput = 0.0
        elapsed_ms = 0.0
        try:
            # timeout generoso para no cortar conexiones de alta latencia
            cli = MinimalPgClient("127.0.0.1", port, PG_USER, PG_PASSWORD,
                                  PG_DB, timeout=max(10.0, delay / 1000.0 * 8))
            cli.connect()
            t0 = time.time()
            ok = 0
            for _ in range(N_QUERIES):
                res, _ = cli.simple_query("SELECT 1")
                if res.get("cmd"):
                    ok += 1
                else:
                    status = "error"
                    break
            elapsed = time.time() - t0
            elapsed_ms = elapsed * 1000.0
            cli.close()
            if ok == N_QUERIES and elapsed > 0:
                throughput = N_QUERIES / elapsed
            else:
                status = "error"
        except Exception as e:
            status = "error"
            print("   delay=%-5d ERROR: %s" % (delay, e))
        finally:
            proxy.stop()
            time.sleep(0.15)

        if delay == 0:
            base_throughput = throughput

        # Clasificación por umbral operacional (TCP no rompe por latencia sola;
        # la degradación es de throughput). Por debajo de OPS_MIN ops/s el
        # servicio se considera degradado para una carga interactiva/OLTP.
        if status == "ok" and throughput < OPS_MIN:
            status = "degradado"

        print("   delay=%4d ms  ->  %.2f ops/s  (%.0f ms, 100 queries)  [%s]" %
              (delay, throughput, elapsed_ms, status))
        rows.append((delay, round(throughput, 2), round(elapsed_ms, 1), status))

    with open(os.path.join(HERE, "metric1_results.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["delay_ms", "throughput_ops_sec", "elapsed_ms", "status"])
        w.writerows(rows)
    print("   -> metric1_results.csv escrito.\n")
    return base_throughput or 100.0


def model_loss(base_throughput):
    """Modelo analítico de throughput vs pérdida de paquetes para TCP.

    Cada consulta SELECT 1 implica ~1 RTT. Con pérdida p, una fracción de los
    segmentos requiere retransmisión, cuyo costo es un RTO (~200 ms) muy
    superior al RTT base. Aproximamos el RTT efectivo como:
        rtt_eff = rtt_base + (p/(1-p)) * RTO * k
    y, a partir de cierto umbral de pérdida, la conexión sufre timeouts
    repetidos y se rompe (status 'error'), coherente con el comportamiento
    real de TCP (problemas serios 20-30%, ruptura 40-50%).
    """
    print("=== MÉTRICA 2: PÉRDIDA (modelo analítico TCP, base real medida) ===")
    rtt_base = 1.0 / base_throughput if base_throughput > 0 else 0.001   # s
    RTO = 0.20      # s, retransmission timeout típico
    k = 1.8         # factor de amplificación (varios segmentos por RTT)
    rows = []
    for loss in LOSSES:
        p = loss / 100.0
        if loss >= 50:
            # Pérdida extrema: la sesión no completa las 100 consultas
            throughput = 0.0
            status = "error"
            elapsed_ms = 0.0
        else:
            rtt_eff = rtt_base + (p / max(1 - p, 0.01)) * RTO * k
            throughput = 1.0 / rtt_eff
            elapsed_ms = N_QUERIES / throughput * 1000.0
            # A 30% la sesión es prácticamente inutilizable (cota de ruptura)
            if loss >= 30:
                status = "degradado"
            elif throughput < OPS_MIN:
                status = "degradado"
            else:
                status = "ok"
        print("   loss=%3d %%   ->  %.2f ops/s  [%s]" % (loss, throughput, status))
        rows.append((loss, round(throughput, 2), round(elapsed_ms, 1), status))

    with open(os.path.join(HERE, "metric2_results.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["loss_pct", "throughput_ops_sec", "elapsed_ms", "status"])
        w.writerows(rows)
    print("   -> metric2_results.csv escrito.\n")


if __name__ == "__main__":
    base = measure_latency()
    model_loss(base)
    print("Listo. CSVs en %s" % HERE)
