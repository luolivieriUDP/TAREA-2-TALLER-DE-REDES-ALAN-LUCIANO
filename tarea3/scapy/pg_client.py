#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================================
 pg_client.py  -  Cliente PostgreSQL mínimo (protocolo v3.0) con SCRAM-SHA-256
 Tarea 3 - Taller de Redes y Servicios (UDP)
----------------------------------------------------------------------------
 Implementa lo justo del protocolo frontend/backend para:
   - negociar (SSLRequest -> 'N')
   - enviar el StartupMessage
   - autenticarse con SCRAM-SHA-256 (RFC 5802 / 7677)
   - enviar UNA consulta simple ('Q') y leer la respuesta del servidor.

 Se usa como "driver" automático de los scripts mod_*.py: a diferencia de
 psycopg2 (que envía consultas internas de configuración), aquí controlamos
 con exactitud qué mensaje 'Q' viaja por el proxy, lo que produce salidas
 limpias y deterministas para el informe.
============================================================================
"""
import socket
import struct
import hashlib
import hmac
import base64
import os
import time


def _hmac(key, msg):
    return hmac.new(key, msg, hashlib.sha256).digest()


def _h(msg):
    return hashlib.sha256(msg).digest()


class PgError(Exception):
    pass


class MinimalPgClient:
    def __init__(self, host, port, user, password, database, timeout=10.0):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.timeout = timeout
        self.sock = None
        self._buf = b""

    # ------------------------------------------------------------------
    def connect(self):
        self.sock = socket.create_connection((self.host, self.port),
                                             timeout=self.timeout)
        self.sock.settimeout(self.timeout)
        self._ssl_request()
        self._startup()
        self._authenticate()
        self._read_until_ready()      # ParameterStatus, BackendKeyData, Z
        return self

    # ------------------------------------------------------------------
    def _ssl_request(self):
        # SSLRequest: length=8, code=80877103 -> servidor responde 'S' o 'N'
        self.sock.sendall(struct.pack(">II", 8, 80877103))
        r = self.sock.recv(1)
        if r not in (b"N", b"S"):
            raise PgError("Respuesta SSLRequest inesperada: %r" % r)
        # Continuamos en texto plano (servidor sin TLS, igual que en Tarea 2)

    # ------------------------------------------------------------------
    def _startup(self):
        protocol = (3 << 16) | 0
        params = ("user\x00%s\x00database\x00%s\x00application_name\x00mitm_client\x00"
                  % (self.user, self.database)).encode() + b"\x00"
        length = 4 + 4 + len(params)
        self.sock.sendall(struct.pack(">II", length, protocol) + params)

    # ------------------------------------------------------------------
    def _recv_message(self):
        """Lee un mensaje completo del backend: tipo(1) + length(4) + body."""
        while len(self._buf) < 5:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise PgError("conexión cerrada por el servidor")
            self._buf += chunk
        mtype = self._buf[0:1]
        (length,) = struct.unpack(">I", self._buf[1:5])
        total = 1 + length
        while len(self._buf) < total:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise PgError("conexión cerrada (mensaje incompleto)")
            self._buf += chunk
        body = self._buf[5:total]
        self._buf = self._buf[total:]
        return mtype, body

    # ------------------------------------------------------------------
    def _authenticate(self):
        mtype, body = self._recv_message()
        if mtype != b"R":
            raise PgError("Se esperaba Authentication ('R'), llegó %r" % mtype)
        (authcode,) = struct.unpack(">I", body[0:4])
        if authcode == 0:
            return                                  # AuthenticationOk (trust)
        if authcode != 10:                          # 10 = AuthenticationSASL
            raise PgError("Método de auth no soportado: %d" % authcode)

        # SCRAM-SHA-256
        client_nonce = base64.b64encode(os.urandom(18)).decode()
        client_first_bare = "n=,r=%s" % client_nonce
        client_first = "n,," + client_first_bare
        mech = b"SCRAM-SHA-256\x00"
        cf = client_first.encode()
        msg = mech + struct.pack(">I", len(cf)) + cf
        self.sock.sendall(b"p" + struct.pack(">I", 4 + len(msg)) + msg)

        # AuthenticationSASLContinue
        mtype, body = self._recv_message()
        if mtype != b"R":
            raise PgError("SCRAM: se esperaba 'R'")
        (authcode,) = struct.unpack(">I", body[0:4])
        server_first = body[4:].decode()
        attrs = dict(kv.split("=", 1) for kv in server_first.split(","))
        combined_nonce = attrs["r"]
        salt = base64.b64decode(attrs["s"])
        iterations = int(attrs["i"])

        salted = hashlib.pbkdf2_hmac("sha256", self.password.encode(),
                                     salt, iterations, 32)
        client_key = _hmac(salted, b"Client Key")
        stored_key = _h(client_key)
        client_final_no_proof = "c=biws,r=%s" % combined_nonce
        auth_message = "%s,%s,%s" % (client_first_bare, server_first,
                                     client_final_no_proof)
        client_sig = _hmac(stored_key, auth_message.encode())
        proof = bytes(a ^ b for a, b in zip(client_key, client_sig))
        client_final = "%s,p=%s" % (client_final_no_proof,
                                    base64.b64encode(proof).decode())
        cfm = client_final.encode()
        self.sock.sendall(b"p" + struct.pack(">I", 4 + len(cfm)) + cfm)

        # AuthenticationSASLFinal + AuthenticationOk
        mtype, body = self._recv_message()
        if mtype != b"R":
            raise PgError("SCRAM: se esperaba SASLFinal")
        # siguiente debe ser AuthenticationOk
        mtype, body = self._recv_message()
        (authcode,) = struct.unpack(">I", body[0:4])
        if authcode != 0:
            raise PgError("SCRAM: autenticación falló")

    # ------------------------------------------------------------------
    def _read_until_ready(self):
        """Consume mensajes hasta ReadyForQuery ('Z')."""
        msgs = []
        while True:
            mtype, body = self._recv_message()
            msgs.append((mtype, body))
            if mtype == b"Z":
                break
        return msgs

    # ------------------------------------------------------------------
    def simple_query(self, sql):
        """Envía una consulta simple ('Q') y devuelve (summary, elapsed_ms)."""
        q = sql.encode() + b"\x00"
        self.sock.sendall(b"Q" + struct.pack(">I", 4 + len(q)) + q)
        t0 = time.time()
        rows, error, cmd = [], None, None
        try:
            while True:
                mtype, body = self._recv_message()
                if mtype == b"D":                  # DataRow
                    rows.append(self._decode_datarow(body))
                elif mtype == b"C":                # CommandComplete
                    cmd = body.rstrip(b"\x00").decode("latin-1")
                elif mtype == b"E":                # ErrorResponse
                    error = self._decode_error(body)
                elif mtype == b"Z":                # ReadyForQuery
                    break
        except socket.timeout:
            elapsed = (time.time() - t0) * 1000.0
            return {"timeout": True, "rows": rows, "cmd": cmd,
                    "error": error}, elapsed
        except PgError as e:
            elapsed = (time.time() - t0) * 1000.0
            return {"closed": str(e), "rows": rows, "cmd": cmd,
                    "error": error}, elapsed
        elapsed = (time.time() - t0) * 1000.0
        return {"rows": rows, "cmd": cmd, "error": error}, elapsed

    # ------------------------------------------------------------------
    @staticmethod
    def _decode_datarow(body):
        (ncols,) = struct.unpack(">H", body[0:2])
        off = 2
        vals = []
        for _ in range(ncols):
            (ln,) = struct.unpack(">i", body[off:off + 4])
            off += 4
            if ln == -1:
                vals.append(None)
            else:
                vals.append(body[off:off + ln].decode("latin-1", "replace"))
                off += ln
        return vals

    @staticmethod
    def _decode_error(body):
        fields = body.split(b"\x00")
        out = {}
        for f in fields:
            if not f:
                continue
            out[chr(f[0])] = f[1:].decode("latin-1", "replace")
        sev = out.get("S", "")
        code = out.get("C", "")
        msg = out.get("M", "")
        return "%s %s: %s" % (sev, code, msg)

    # ------------------------------------------------------------------
    def close(self):
        try:
            if self.sock:
                self.sock.sendall(b"X" + struct.pack(">I", 4))   # Terminate
                self.sock.close()
        except OSError:
            pass
