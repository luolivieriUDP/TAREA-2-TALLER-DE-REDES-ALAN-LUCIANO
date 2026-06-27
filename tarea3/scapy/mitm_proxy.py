#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================================
 mitm_proxy.py  -  Proxy TCP transparente (Man-In-The-Middle) para PostgreSQL
 Tarea 3 - Taller de Redes y Servicios (UDP)
----------------------------------------------------------------------------
 Escucha en PROXY_PORT (5433) y reenvía el tráfico hacia el servidor
 PostgreSQL real (SERVER_HOST:PG_PORT, normalmente servidor:5432).
 El reenvío ocurre en dos hilos independientes (cliente->servidor y
 servidor->cliente) y permite inyectar funciones "hook" que modifican el
 payload al vuelo. Imprime los bytes originales y modificados de cada
 mensaje interceptado.

 Uso como módulo (lo importan mod_1/mod_2/mod_3):
     from mitm_proxy import PgMITMProxy
     proxy = PgMITMProxy(c2s_hook=mi_hook)
     proxy.start()

 Uso directo (proxy "limpio", sin modificación):
     python3 mitm_proxy.py
============================================================================
"""
import os
import socket
import threading
import sys
import time

# ----------------------- CONFIGURACIÓN (editar aquí) -----------------------
LISTEN_HOST = os.environ.get("LISTEN_HOST", "0.0.0.0")
LISTEN_PORT = int(os.environ.get("PROXY_PORT", "5433"))
# En Docker el servidor real es el contenedor "servidor" (alias en redpsql).
# Para pruebas locales fuera de Docker, exporte SERVER_HOST=127.0.0.1
SERVER_HOST = os.environ.get("SERVER_HOST", "servidor")
SERVER_PORT = int(os.environ.get("PG_PORT", "5432"))
BUFSIZE     = 65535
# ---------------------------------------------------------------------------

# Tipos de mensaje del protocolo frontend/backend v3.0 (para impresión legible)
MSG_TYPES = {
    0x51: "Q (Query)",            0x58: "X (Terminate)",
    0x70: "p (PasswordMessage)",  0x52: "R (Authentication)",
    0x5A: "Z (ReadyForQuery)",    0x45: "E (ErrorResponse)",
    0x54: "T (RowDescription)",   0x44: "D (DataRow)",
    0x43: "C (CommandComplete)",  0x53: "S (ParameterStatus)",
    0x4B: "K (BackendKeyData)",   0x4E: "N (NoticeResponse)",
}


def describe(data: bytes) -> str:
    """Devuelve una descripción corta del primer byte de tipo del mensaje."""
    if not data:
        return "(vacío)"
    t = data[0]
    name = MSG_TYPES.get(t, "0x%02x (desconocido)" % t)
    return name


def hexdump(data: bytes, limit: int = 48) -> str:
    """Representación hex de los primeros `limit` bytes."""
    chunk = data[:limit]
    h = " ".join("%02x" % b for b in chunk)
    suffix = " ..." if len(data) > limit else ""
    return h + suffix


class PgMITMProxy:
    """
    Proxy TCP con hooks de modificación de payload.

    client_to_server_hook(data: bytes) -> bytes : modifica lo que el cliente
        envía hacia el servidor (mensajes Q, X, p, etc.).
    server_to_client_hook(data: bytes) -> bytes : modifica lo que el servidor
        responde hacia el cliente (mensajes T, D, C, Z, E, ...).
    """

    def __init__(self, listen_host=LISTEN_HOST, listen_port=LISTEN_PORT,
                 server_host=SERVER_HOST, server_port=SERVER_PORT,
                 client_to_server_hook=None, server_to_client_hook=None,
                 verbose=True, delay_c2s_ms=0.0):
        self.listen_host = listen_host
        self.listen_port = listen_port
        self.server_host = server_host
        self.server_port = server_port
        self.c2s_hook = client_to_server_hook
        self.s2c_hook = server_to_client_hook
        self.verbose = verbose
        # Retardo artificial (ms) aplicado en el sentido cliente->servidor.
        # Emula "tc qdisc netem delay" cuando no se dispone de Linux/tc.
        self.delay_c2s_ms = delay_c2s_ms
        self._srv_sock = None
        self._stop = threading.Event()

    # --------------------------------------------------------------------
    def log(self, *args):
        if self.verbose:
            print(*args, flush=True)

    # --------------------------------------------------------------------
    def start(self):
        """Acepta conexiones en bucle infinito hasta recibir stop()."""
        self._srv_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._srv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._srv_sock.bind((self.listen_host, self.listen_port))
        self._srv_sock.listen(16)
        self._srv_sock.settimeout(1.0)
        self.log("[proxy] Escuchando en %s:%d  ->  %s:%d" % (
            self.listen_host, self.listen_port,
            self.server_host, self.server_port))
        try:
            while not self._stop.is_set():
                try:
                    client_sock, addr = self._srv_sock.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                t = threading.Thread(target=self.handle_client,
                                     args=(client_sock, addr), daemon=True)
                t.start()
        finally:
            try:
                self._srv_sock.close()
            except OSError:
                pass

    # --------------------------------------------------------------------
    def stop(self):
        self._stop.set()
        try:
            if self._srv_sock:
                self._srv_sock.close()
        except OSError:
            pass

    # --------------------------------------------------------------------
    def handle_client(self, client_sock, addr):
        """Por cada cliente, abre la conexión al servidor real y lanza dos
        hilos de relay (uno por sentido)."""
        self.log("[proxy] Nueva conexión desde %s:%d" % addr)
        try:
            server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_sock.connect((self.server_host, self.server_port))
        except OSError as e:
            self.log("[proxy] No se pudo conectar al servidor real: %s" % e)
            try:
                client_sock.close()
            except OSError:
                pass
            return

        t1 = threading.Thread(target=self._relay,
                              args=(client_sock, server_sock,
                                    self.c2s_hook, "C->S"), daemon=True)
        t2 = threading.Thread(target=self._relay,
                              args=(server_sock, client_sock,
                                    self.s2c_hook, "S->C"), daemon=True)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        for s in (client_sock, server_sock):
            try:
                s.close()
            except OSError:
                pass
        self.log("[proxy] Conexión %s:%d cerrada" % addr)

    # --------------------------------------------------------------------
    def _relay(self, src, dst, hook, direction):
        """Bucle de reenvío con aplicación del hook. Tolerante a errores."""
        try:
            while not self._stop.is_set():
                try:
                    data = src.recv(BUFSIZE)
                except (ConnectionResetError, OSError):
                    break
                if not data:
                    break                      # cierre ordenado del extremo

                out = data
                if hook is not None:
                    try:
                        out = hook(data)
                    except Exception as e:     # un hook nunca debe tumbar el proxy
                        self.log("[proxy][%s] hook lanzó excepción: %s" %
                                 (direction, e))
                        out = data

                if out is not data and out != data:
                    self.log("[proxy][%s] MODIFICADO  %s" % (direction, describe(data)))
                    self.log("            original (%d B): %s" % (len(data), hexdump(data)))
                    self.log("            modificado(%d B): %s" % (len(out), hexdump(out)))

                # Retardo artificial (netem-like) en el sentido cliente->servidor
                if direction == "C->S" and self.delay_c2s_ms > 0:
                    time.sleep(self.delay_c2s_ms / 1000.0)

                try:
                    if out:
                        dst.sendall(out)
                except (ConnectionResetError, OSError):
                    break
        finally:
            # Cerrar el lado de escritura para desbloquear al otro hilo
            for s in (src, dst):
                try:
                    s.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass


# ===========================================================================
if __name__ == "__main__":
    # Proxy "limpio" (sin modificación): útil para verificar que psql puede
    # conectarse a través del proxy igual que directamente al servidor.
    print("=== Proxy MITM PostgreSQL (modo passthrough) ===")
    print("Servidor real: %s:%d   |   Escuchando en :%d" %
          (SERVER_HOST, SERVER_PORT, LISTEN_PORT))
    proxy = PgMITMProxy()
    try:
        proxy.start()
    except KeyboardInterrupt:
        print("\n[proxy] Detenido por el usuario.")
        proxy.stop()
        sys.exit(0)
