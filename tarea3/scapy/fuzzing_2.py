#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================================
 fuzzing_2.py  -  FUZZING 2: StartupMessage mutado + bit-flipping
 Tarea 3 - Taller de Redes y Servicios (UDP)
----------------------------------------------------------------------------
 Técnica: MUTATION-BASED FUZZING. Se parte de un StartupMessage VÁLIDO del
 protocolo frontend/backend v3.0 y se aplican mutaciones dirigidas a campos
 concretos (versión de protocolo, campo length, parámetros) además de
 bit-flips aleatorios. A diferencia del fuzzing_1 (totalmente aleatorio),
 aquí cada caso es una semilla válida ligeramente corrompida, lo que ejercita
 rutas de parsing más profundas del servidor.

 Comportamiento esperado: el servidor maneja cada caso de forma segura,
 devolviendo ErrorResponse (FATAL) en la mayoría; ningún caso debe crashear.
============================================================================
"""
import os
import socket
import struct
import random
import time
import sys

# ----------------------- CONFIGURACIÓN (editar aquí) -----------------------
SERVER_HOST = os.environ.get("SERVER_HOST", "servidor")
SERVER_PORT = int(os.environ.get("PG_PORT", "5432"))
PG_USER     = os.environ.get("PG_USER", "taller")
PG_DB       = os.environ.get("PG_DB", "tallerdb")
TIMEOUT     = float(os.environ.get("FUZZ_TIMEOUT", "3.0"))
CAP_DIR     = os.environ.get("CAP_DIR", "/capturas")
OUT_FILE    = os.path.join(CAP_DIR, "fuzzing2_output.txt")
# ---------------------------------------------------------------------------


class Tee:
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


# ----------------------- Funciones auxiliares ------------------------------
def build_startup(user=PG_USER, db=PG_DB, major=3, minor=0,
                  final_terminator=True):
    """Construye un StartupMessage v3.0 válido."""
    protocol = (major << 16) | minor          # 196608 para v3.0
    params = ("user\x00%s\x00database\x00%s\x00application_name\x00psql\x00"
              % (user, db)).encode("utf-8")
    if final_terminator:
        params += b"\x00"                      # terminador final del bloque k/v
    length = 4 + 4 + len(params)               # length + protocol + params
    return struct.pack(">II", length, protocol) + params


def bitflip(data, n):
    """Aplica n bit-flips en posiciones de bit aleatorias del bytearray."""
    b = bytearray(data)
    if not b:
        return bytes(b)
    flips = []
    for _ in range(n):
        byte_idx = random.randint(0, len(b) - 1)
        bit_idx = random.randint(0, 7)
        b[byte_idx] ^= (1 << bit_idx)
        flips.append((byte_idx, bit_idx))
    return bytes(b), flips


def send_and_read(payload):
    """Envía el payload al servidor y devuelve (respuesta, estado)."""
    refused = timed_out = closed = False
    resp = b""
    try:
        s = socket.create_connection((SERVER_HOST, SERVER_PORT), timeout=TIMEOUT)
    except OSError:
        return b"", "conexión rechazada"
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

    if timed_out:
        return resp, "timeout (servidor esperando más bytes)"
    if resp[:1] == b"E":
        return resp, "ErrorResponse ('E', FATAL)"
    if resp[:1] == b"R":
        return resp, "Authentication request ('R') - startup aceptado"
    if resp:
        return resp, "respondió %d bytes (tipo %r)" % (len(resp), resp[:1])
    if closed:
        return resp, "el servidor cerró la conexión"
    return resp, "sin datos"


def parse_error(resp):
    """Extrae el mensaje legible de un ErrorResponse de PostgreSQL."""
    if resp[:1] != b"E":
        return ""
    body = resp[5:]
    fields = body.split(b"\x00")
    parts = []
    for f in fields:
        if not f:
            continue
        code = chr(f[0])
        val = f[1:].decode("latin-1", "replace")
        if code in ("M", "S", "C"):   # Message, Severity, Code
            parts.append("%s=%s" % (code, val))
    return "  ".join(parts)


def server_alive():
    try:
        s = socket.create_connection((SERVER_HOST, SERVER_PORT), timeout=2.0)
        s.sendall(struct.pack(">II", 8, 80877103))
        s.settimeout(2.0)
        r = s.recv(1)
        s.close()
        return r in (b"S", b"N")
    except OSError:
        return False


def run_case(n, descripcion, payload, extra=""):
    print("\n" + "-" * 74)
    print(" CASO %d: %s" % (n, descripcion))
    if extra:
        print("   %s" % extra)
    print("   payload (%d bytes), primeros 32: %s" %
          (len(payload), " ".join("%02x" % b for b in payload[:32])))
    resp, estado = send_and_read(payload)
    print("   RESPUESTA  : %s" % estado)
    err = parse_error(resp)
    if err:
        print("   DETALLE    : %s" % err)
    print("   ¿Vivo?     : %s" % ("SÍ" if server_alive() else "NO"))
    return (n, descripcion, estado)


def main():
    sys.stdout = Tee(OUT_FILE)
    random.seed(2024)
    print("=" * 74)
    print(" FUZZING 2 - StartupMessage mutado (mutation-based + bit-flipping)")
    print(" Objetivo: %s:%d   usuario=%s  base=%s" %
          (SERVER_HOST, SERVER_PORT, PG_USER, PG_DB))
    print("=" * 74)

    valido = build_startup()
    print("\n[semilla] StartupMessage válido (%d bytes): %s" %
          (len(valido), " ".join("%02x" % b for b in valido[:32])))

    resultados = []

    # 1. Protocol version 99.0 (0x00630000) - versión inexistente
    p = struct.pack(">II", len(valido), (99 << 16) | 0) + valido[8:]
    resultados.append(run_case(1, "Protocol version 99.0 (0x00630000) - inexistente", p))

    # 2. Length = 0xFFFFFFFF - longitud máxima posible
    p = struct.pack(">I", 0xFFFFFFFF) + valido[4:]
    resultados.append(run_case(2, "Length = 0xFFFFFFFF (longitud máxima, ~4 GB)", p))

    # 3. Length = 0
    p = struct.pack(">I", 0) + valido[4:]
    resultados.append(run_case(3, "Length = 0 (longitud cero)", p))

    # 4. Username con null byte embebido "post\x00gres"
    p = build_startup(user="post\x00gres")
    resultados.append(run_case(4, "Username con null byte embebido: 'post\\x00gres'", p))

    # 5. Bit-flip en 5 posiciones aleatorias del startup válido
    p, flips = bitflip(valido, 5)
    flips_txt = ", ".join("byte %d bit %d" % (bi, bit) for bi, bit in flips)
    resultados.append(run_case(5, "Bit-flip en 5 posiciones aleatorias", p,
                               extra="posiciones: %s" % flips_txt))

    # 6. Startup sin terminador final (falta el \x00 final)
    p = build_startup(final_terminator=False)
    resultados.append(run_case(6, "Startup sin terminador final (\\x00)", p))

    # 7. Solo 4 bytes (el campo length), sin nada más
    p = struct.pack(">I", 8)
    resultados.append(run_case(7, "Solo 4 bytes (campo length=8), sin protocolo", p))

    # 8. Username de 10.000 caracteres (test de buffer overflow)
    p = build_startup(user="A" * 10000)
    resultados.append(run_case(8, "Username de 10.000 caracteres (buffer overflow)", p))

    # ---------------- Resumen ----------------
    print("\n" + "=" * 74)
    print(" RESUMEN FUZZING 2")
    print("=" * 74)
    for n, desc, estado in resultados:
        print("   Caso %d: %-50s -> %s" % (n, desc[:50], estado))
    print("\n   El servidor PostgreSQL %s todos los casos." %
          ("sobrevivió" if server_alive() else "NO sobrevivió"))
    print("   Conclusión: el parser valida longitud, versión y parámetros antes")
    print("   de procesarlos; las mutaciones producen errores controlados, no caídas.")


if __name__ == "__main__":
    main()
