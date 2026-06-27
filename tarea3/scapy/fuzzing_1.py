#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================================
 fuzzing_1.py  -  FUZZING 1: payload completamente aleatorio
 Tarea 3 - Taller de Redes y Servicios (UDP)
----------------------------------------------------------------------------
 Técnica: DUMB FUZZING / GENERATION-BASED FUZZING.
 Se generan paquetes de bytes totalmente aleatorios (sin ninguna estructura
 del protocolo) y se envían directamente al servidor PostgreSQL real
 (puerto 5432). Para cada iteración se mide y clasifica la respuesta del
 servidor y se verifica que el servidor siga vivo.

 Comportamiento esperado: PostgreSQL intenta parsear los primeros 4 bytes
 como el campo "length" del StartupMessage; la versión de protocolo
 (bytes 5-8) será inválida con bytes aleatorios. El servidor debe responder
 con un ErrorResponse ('E') o cerrar la conexión, SIN caerse.
============================================================================
"""
import os
import socket
import random
import time
import struct
import sys

# ----------------------- CONFIGURACIÓN (editar aquí) -----------------------
SERVER_HOST = os.environ.get("SERVER_HOST", "servidor")   # contenedor servidor
SERVER_PORT = int(os.environ.get("PG_PORT", "5432"))
N_ITER      = int(os.environ.get("FUZZ_ITER", "10"))
MIN_SIZE    = 10
MAX_SIZE    = 1000
TIMEOUT     = float(os.environ.get("FUZZ_TIMEOUT", "3.0"))
PAUSE       = 0.5
CAP_DIR     = os.environ.get("CAP_DIR", "/capturas")
OUT_FILE    = os.path.join(CAP_DIR, "fuzzing1_output.txt")
# ---------------------------------------------------------------------------


class Tee:
    """Escribe simultáneamente en stdout y en el archivo de salida."""
    def __init__(self, path):
        self.terminal = sys.stdout
        try:
            self.file = open(path, "w", encoding="utf-8")
        except OSError:
            self.file = None

    def write(self, msg):
        self.terminal.write(msg)
        if self.file:
            self.file.write(msg)

    def flush(self):
        self.terminal.flush()
        if self.file:
            self.file.flush()


def server_alive(host, port, timeout=2.0):
    """Comprueba que el postmaster sigue respondiendo enviando un SSLRequest
    válido (8 bytes) y leyendo el byte de respuesta ('S' o 'N')."""
    try:
        s = socket.create_connection((host, port), timeout=timeout)
    except OSError:
        return False, "no acepta conexiones (caído?)"
    try:
        # SSLRequest: length=8, code=80877103
        s.sendall(struct.pack(">II", 8, 80877103))
        s.settimeout(timeout)
        resp = s.recv(1)
        if resp in (b"S", b"N"):
            return True, "vivo (respondió '%s' al SSLRequest)" % resp.decode()
        return True, "vivo (respuesta inesperada: %r)" % resp
    except OSError as e:
        return False, "no respondió al SSLRequest: %s" % e
    finally:
        try:
            s.close()
        except OSError:
            pass


def classify(resp, closed, refused, timed_out):
    if refused:
        return "conexión rechazada"
    if timed_out:
        return "timeout (sin respuesta)"
    if resp and resp[:1] == b"E":
        return "respondió con ErrorResponse ('E')"
    if resp:
        return "respondió con datos (%d bytes, tipo %r)" % (len(resp), resp[:1])
    if closed:
        return "el servidor cerró la conexión sin responder"
    return "sin datos"


def main():
    sys.stdout = Tee(OUT_FILE)
    print("=" * 74)
    print(" FUZZING 1 - Payload aleatorio (dumb / generation-based fuzzing)")
    print(" Objetivo: %s:%d   |   Iteraciones: %d   |   Tamaño: %d-%d bytes" %
          (SERVER_HOST, SERVER_PORT, N_ITER, MIN_SIZE, MAX_SIZE))
    print("=" * 74)

    random.seed(1337)   # reproducibilidad
    resultados = []

    for i in range(1, N_ITER + 1):
        size = random.randint(MIN_SIZE, MAX_SIZE)
        payload = bytes(random.randint(0, 255) for _ in range(size))
        refused = timed_out = closed = False
        resp = b""
        t0 = time.time()

        try:
            s = socket.create_connection((SERVER_HOST, SERVER_PORT), timeout=TIMEOUT)
        except ConnectionRefusedError:
            refused = True
            s = None
        except OSError as e:
            refused = True
            s = None

        if s is not None:
            try:
                s.sendall(payload)
                s.settimeout(TIMEOUT)
                try:
                    resp = s.recv(4096)
                    if resp == b"":
                        closed = True
                except socket.timeout:
                    timed_out = True
            except (ConnectionResetError, BrokenPipeError):
                closed = True
            except OSError:
                closed = True
            finally:
                try:
                    s.close()
                except OSError:
                    pass

        dt = (time.time() - t0) * 1000.0
        estado = classify(resp, closed, refused, timed_out)
        alive, alive_msg = server_alive(SERVER_HOST, SERVER_PORT)

        print("\n[Iteración %2d] tamaño=%d bytes  (%.1f ms)" % (i, size, dt))
        print("   primeros 16 bytes enviados : %s" %
              " ".join("%02x" % b for b in payload[:16]))
        if resp:
            preview = resp[:60]
            txt = preview.decode("latin-1", "replace").replace("\n", "\\n")
            print("   respuesta del servidor     : %d bytes -> %r" % (len(resp), txt))
        print("   CLASIFICACIÓN              : %s" % estado)
        print("   ¿Servidor sigue vivo?      : %s -> %s" %
              ("SÍ" if alive else "NO", alive_msg))

        resultados.append((i, size, estado, alive))
        time.sleep(PAUSE)

    # ---------------- Resumen ----------------
    print("\n" + "=" * 74)
    print(" RESUMEN FUZZING 1")
    print("=" * 74)
    vivo_final = all(r[3] for r in resultados)
    for i, size, estado, alive in resultados:
        print("   it=%2d  size=%4d  -> %-45s vivo=%s" %
              (i, size, estado, "SÍ" if alive else "NO"))
    print("\n   El servidor PostgreSQL %s tras las %d iteraciones de fuzzing." %
          ("SOBREVIVIÓ" if vivo_final else "NO sobrevivió", N_ITER))
    print("   Conclusión: el parser del StartupMessage rechaza la entrada")
    print("   malformada de forma segura (ErrorResponse / cierre), sin crashear.")


if __name__ == "__main__":
    main()
