#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================================
 mod_2_length.py  -  MODIFICACIÓN 2: campo LENGTH del mensaje
 Tarea 3 - Taller de Redes y Servicios (UDP)
----------------------------------------------------------------------------
 El proxy MITM intercepta los mensajes Query ('Q') y altera los 4 bytes de
 longitud (bytes 1..4), dejando el resto del mensaje intacto:

   Caso A: length_real + 1000   (el server cree que faltan 1000 bytes)
   Caso B: length_real - 4      (longitud demasiado corta)
   Caso C: 0xFFFFFFFF           (longitud máxima, ~4 GB)

 FUNDAMENTACIÓN DEL COMPORTAMIENTO ESPERADO
 El servidor lee el campo length para saber cuántos bytes consumir del
 stream TCP. Con length_fake > length_real (Caso A) el backend queda
 esperando bytes que nunca llegarán y la sesión se bloquea hasta un timeout.
 Con length absurdamente grande (Caso C) PostgreSQL valida el límite y
 aborta con "invalid message length". El postmaster no se cae: cada sesión
 corre en un proceso hijo independiente.

 Para cada caso se mide: tiempo hasta respuesta/timeout, error devuelto y si
 la sesión se recupera o queda bloqueada.
============================================================================
"""
import os
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
BLOCK_TIMEOUT = float(os.environ.get("BLOCK_TIMEOUT", "4.0"))
CAP_DIR     = os.environ.get("CAP_DIR", "/capturas")
OUT_FILE    = os.path.join(CAP_DIR, "mod2_output.txt")
# ---------------------------------------------------------------------------

CASES = {
    "A": ("length_real + 1000 (faltan 1000 bytes)", "add", 1000),
    "B": ("length_real - 4 (longitud demasiado corta)", "sub", 4),
    "C": ("0xFFFFFFFF (longitud máxima, ~4 GB)", "max", 0),
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


def make_hook(mode, delta):
    state = {"done": False}

    def hook(data):
        if not state["done"] and data[:1] == b"Q" and len(data) >= 5:
            state["done"] = True
            real = struct.unpack(">I", data[1:5])[0]
            if mode == "add":
                new = real + delta
            elif mode == "sub":
                new = max(real - delta, 0)
            else:
                new = 0xFFFFFFFF
            new &= 0xFFFFFFFF
            print("   [hook] length real=%d -> length falso=%d (0x%08X)" %
                  (real, new, new))
            return data[:1] + struct.pack(">I", new) + data[5:]
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


def server_alive():
    try:
        s = socket.create_connection((SERVER_HOST, PG_PORT), timeout=2.0)
        s.sendall(struct.pack(">II", 8, 80877103))
        s.settimeout(2.0)
        r = s.recv(1)
        s.close()
        return r in (b"S", b"N")
    except OSError:
        return False


def run_case(case_key):
    desc, mode, delta = CASES[case_key]
    port = PROXY_PORT + ord(case_key) - ord("A")
    print("\n" + "=" * 74)
    print(" CASO %s: %s" % (case_key, desc))
    print("=" * 74)

    proxy = PgMITMProxy(listen_port=port, server_host=SERVER_HOST,
                        server_port=PG_PORT,
                        client_to_server_hook=make_hook(mode, delta),
                        verbose=False)
    threading.Thread(target=proxy.start, daemon=True).start()
    wait_port("127.0.0.1", port)

    print("   Cliente envía: Query 'SELECT 1' (timeout cliente=%.1fs)" % BLOCK_TIMEOUT)
    t0 = time.time()
    estado_sesion = "?"
    try:
        cli = MinimalPgClient("127.0.0.1", port, PG_USER, PG_PASSWORD, PG_DB,
                              timeout=BLOCK_TIMEOUT)
        cli.connect()
        res, ms = cli.simple_query("SELECT 1")
        print("   Tiempo de respuesta: %.1f ms" % ms)
        if res.get("timeout"):
            print("       RESULTADO: TIMEOUT -> el backend quedó BLOQUEADO esperando")
            print("                  los bytes extra que nunca llegaron.")
            estado_sesion = "bloqueada (timeout)"
        elif res.get("error"):
            print("       ErrorResponse -> %s" % res["error"])
            estado_sesion = "error controlado"
        elif res.get("closed"):
            print("       Conexión cerrada -> %s" % res["closed"])
            estado_sesion = "cerrada por el servidor"
        elif res.get("cmd"):
            print("       CommandComplete: %s  filas=%s" %
                  (res["cmd"], res.get("rows")))
            estado_sesion = "ejecutada normalmente (inesperado)"
        cli.close()
    except Exception as e:
        dt = (time.time() - t0) * 1000.0
        print("   La conexión terminó tras %.1f ms con -> %s: %s" %
              (dt, type(e).__name__, e))
        estado_sesion = "excepción en el cliente"

    alive = server_alive()
    print("   ¿Se recupera la sesión?  -> %s" % estado_sesion)
    print("   ¿Servidor sigue vivo?    -> %s" % ("SÍ" if alive else "NO"))
    proxy.stop()
    time.sleep(0.2)


def main():
    if AUTO:
        sys.stdout = Tee(OUT_FILE)
    print("##########################################################################")
    print("# MODIFICACIÓN 2 - Campo LENGTH del mensaje (proxy MITM en :%d)" % PROXY_PORT)
    print("# Servidor real: %s:%d" % (SERVER_HOST, PG_PORT))
    print("##########################################################################")

    if not AUTO:
        case_key = os.environ.get("MITM_CASE", "A").upper()
        desc, mode, delta = CASES[case_key]
        print("[DEMO] Caso %s activo: %s" % (case_key, desc))
        print("[DEMO] Conéctese con:  psql -h <host_scapy> -p %d -U %s -d %s" %
              (PROXY_PORT, PG_USER, PG_DB))
        proxy = PgMITMProxy(listen_port=PROXY_PORT, server_host=SERVER_HOST,
                            server_port=PG_PORT,
                            client_to_server_hook=make_hook(mode, delta))
        try:
            proxy.start()
        except KeyboardInterrupt:
            proxy.stop()
        return

    for k in ("A", "B", "C"):
        run_case(k)

    print("\n" + "#" * 74)
    print("# Conclusión: el campo length controla el framing del protocolo. Un length")
    print("# mayor que el real bloquea la sesión (el server espera datos que no llegan);")
    print("# un length absurdo dispara la validación 'invalid message length'. En ningún")
    print("# caso cae el servidor: el aislamiento por proceso contiene el daño.")
    print("#" * 74)


if __name__ == "__main__":
    main()
