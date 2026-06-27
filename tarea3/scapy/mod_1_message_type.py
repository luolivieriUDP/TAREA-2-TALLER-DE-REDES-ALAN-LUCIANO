#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================================
 mod_1_message_type.py  -  MODIFICACIÓN 1: byte de TIPO de mensaje
 Tarea 3 - Taller de Redes y Servicios (UDP)
----------------------------------------------------------------------------
 El proxy MITM intercepta los mensajes Query ('Q', 0x51) que el cliente
 envía y reemplaza SOLO su primer byte (el tipo) por otro:

   Caso A: 'Q' (0x51) -> 'X'  (0x58, Terminate)
   Caso B: 'Q' (0x51) -> 0xFF (tipo inexistente)
   Caso C: 'Q' (0x51) -> 'p'  (0x70, PasswordMessage)

 FUNDAMENTACIÓN DEL COMPORTAMIENTO ESPERADO
 - Caso A (Q->X): el servidor interpreta un Terminate y cierra la conexión
   limpiamente; el cliente no recibe resultados.
 - Caso B (Q->0xFF): tipo desconocido; PostgreSQL aborta con un error FATAL
   de protocolo ("invalid frontend message type") y cierra la conexión.
 - Caso C (Q->p): el backend, ya autenticado, recibe un PasswordMessage
   fuera de contexto; tampoco es un tipo válido en el bucle de comandos, así
   que genera un error FATAL de protocolo.

 Modo de uso:
   - AUTO (por defecto): lanza el proxy y un cliente interno que envía la
     consulta a través de él, mostrando la respuesta real del servidor.
   - DEMO en vivo (MITM_AUTO=0): solo lanza el proxy; conéctese con psql:
        psql -h <scapy> -p 5433 -U taller -d tallerdb
============================================================================
"""
import os
import sys
import time
import threading

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
OUT_FILE    = os.path.join(CAP_DIR, "mod1_output.txt")
# ---------------------------------------------------------------------------

CASES = {
    "A": (0x58, "'Q' (0x51) -> 'X' (0x58, Terminate)"),
    "B": (0xFF, "'Q' (0x51) -> 0xFF (tipo inexistente)"),
    "C": (0x70, "'Q' (0x51) -> 'p' (0x70, PasswordMessage)"),
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


def make_hook(new_type):
    """Devuelve un hook C->S que cambia el byte de tipo de los mensajes 'Q'."""
    state = {"done": False}

    def hook(data):
        if not state["done"] and data[:1] == b"Q":
            state["done"] = True
            modificado = bytes([new_type]) + data[1:]
            print("   [hook] 'Q' (0x51) -> 0x%02X   (mensaje Query reescrito)" % new_type)
            return modificado
        return data
    return hook


def wait_port(host, port, tries=50):
    for _ in range(tries):
        try:
            import socket
            s = socket.create_connection((host, port), timeout=0.2)
            s.close()
            return True
        except OSError:
            time.sleep(0.05)
    return False


def run_case(case_key):
    new_type, desc = CASES[case_key]
    port = PROXY_PORT + ord(case_key) - ord("A")     # 5433, 5434, 5435
    print("\n" + "=" * 74)
    print(" CASO %s: %s" % (case_key, desc))
    print("=" * 74)

    proxy = PgMITMProxy(listen_port=port, server_host=SERVER_HOST,
                        server_port=PG_PORT, client_to_server_hook=make_hook(new_type),
                        verbose=False)
    t = threading.Thread(target=proxy.start, daemon=True)
    t.start()
    wait_port("127.0.0.1", port)

    print("   Cliente envía: Query 'SELECT 1' (a través del proxy :%d)" % port)
    try:
        cli = MinimalPgClient("127.0.0.1", port, PG_USER, PG_PASSWORD, PG_DB,
                              timeout=5.0)
        cli.connect()
        res, ms = cli.simple_query("SELECT 1")
        print("   Respuesta del servidor (%.1f ms):" % ms)
        if res.get("error"):
            print("       ErrorResponse -> %s" % res["error"])
        if res.get("closed"):
            print("       Conexión cerrada por el servidor -> %s" % res["closed"])
        if res.get("timeout"):
            print("       TIMEOUT: el servidor no respondió (sesión bloqueada)")
        if res.get("rows"):
            print("       filas: %s" % res["rows"])
        if res.get("cmd"):
            print("       CommandComplete: %s" % res["cmd"])
        if not any(res.get(k) for k in ("error", "closed", "timeout", "rows", "cmd")):
            print("       (sin respuesta interpretable)")
        cli.close()
    except Exception as e:
        print("   Cliente: la conexión terminó con -> %s: %s" %
              (type(e).__name__, e))
    finally:
        proxy.stop()
        time.sleep(0.2)


def main():
    if AUTO:
        sys.stdout = Tee(OUT_FILE)
    print("##########################################################################")
    print("# MODIFICACIÓN 1 - Byte de TIPO de mensaje (proxy MITM en :%d)" % PROXY_PORT)
    print("# Servidor real: %s:%d" % (SERVER_HOST, PG_PORT))
    print("##########################################################################")

    if not AUTO:
        # Modo demo en vivo: un solo caso, esperar a psql externo
        case_key = os.environ.get("MITM_CASE", "A").upper()
        new_type, desc = CASES[case_key]
        print("[DEMO] Caso %s activo: %s" % (case_key, desc))
        print("[DEMO] Conéctese con:  psql -h <host_scapy> -p %d -U %s -d %s" %
              (PROXY_PORT, PG_USER, PG_DB))
        proxy = PgMITMProxy(listen_port=PROXY_PORT, server_host=SERVER_HOST,
                            server_port=PG_PORT,
                            client_to_server_hook=make_hook(new_type))
        try:
            proxy.start()
        except KeyboardInterrupt:
            proxy.stop()
        return

    for k in ("A", "B", "C"):
        run_case(k)

    print("\n" + "#" * 74)
    print("# Conclusión: corromper el byte de tipo rompe la sincronía del flujo de")
    print("# mensajes. El servidor reacciona con cierre (Terminate) o error FATAL de")
    print("# protocolo, pero el proceso postmaster NO se cae (cada sesión es un fork).")
    print("#" * 74)


if __name__ == "__main__":
    main()
