#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================================
 sniffer_scapy.py  -  Interceptación y disección del tráfico con SCAPY
 Tarea 3 - Taller de Redes y Servicios (UDP)
----------------------------------------------------------------------------
 Usa Scapy para SNIFFAR el tráfico PostgreSQL que circula entre el cliente y
 el servidor en la red redpsql, y diseca cada segmento TCP identificando el
 tipo de mensaje del protocolo frontend/backend (Q, T, D, C, Z, E, p, R, ...).

 Cumple el objetivo del enunciado "interceptar con Scapy el tráfico generado
 entre sus aplicaciones". La MODIFICACIÓN activa se realiza con el proxy MITM
 (mitm_proxy.py): reescribir un stream TCP con estado requiere terminar la
 conexión TCP, algo que la inyección de paquetes sueltos de Scapy no hace de
 forma fiable; por eso se combinan ambas herramientas.

 Debe ejecutarse DENTRO del contenedor scapy (privileged, NET_RAW) sobre la
 interfaz de la red redpsql:

     docker exec -it scapy_mitm python3 /scripts/sniffer_scapy.py
     # en otra terminal, generar tráfico:
     docker exec -it psql-cliente psql -h servidor -U taller -d tallerdb -c "SELECT * FROM routers;"
============================================================================
"""
import os
import sys

try:
    from scapy.all import sniff, TCP, Raw, IP
except ImportError:
    sys.exit("Scapy no está instalado. Use el contenedor scapy_mitm.")

# ----------------------- CONFIGURACIÓN (editar aquí) -----------------------
IFACE   = os.environ.get("SNIFF_IFACE", "eth0")   # interfaz en redpsql
PG_PORT = int(os.environ.get("PG_PORT", "5432"))
COUNT   = int(os.environ.get("SNIFF_COUNT", "0")) # 0 = infinito (Ctrl-C)
# ---------------------------------------------------------------------------

# Tipos de mensaje del protocolo frontend/backend v3.0
MSG = {
    0x51: "Q  Query (cliente)",        0x58: "X  Terminate (cliente)",
    0x70: "p  PasswordMessage (cli)",  0x52: "R  Authentication (srv)",
    0x5A: "Z  ReadyForQuery (srv)",    0x45: "E  ErrorResponse (srv)",
    0x54: "T  RowDescription (srv)",   0x44: "D  DataRow (srv)",
    0x43: "C  CommandComplete (srv)",  0x53: "S  ParameterStatus (srv)",
    0x4B: "K  BackendKeyData (srv)",   0x4E: "N  NoticeResponse (srv)",
}


def dissect(pkt):
    if not pkt.haslayer(TCP) or not pkt.haslayer(Raw):
        return
    tcp = pkt[TCP]
    if PG_PORT not in (tcp.sport, tcp.dport):
        return
    payload = bytes(pkt[Raw].load)
    src = "%s:%d" % (pkt[IP].src, tcp.sport) if pkt.haslayer(IP) else "?"
    dst = "%s:%d" % (pkt[IP].dst, tcp.dport) if pkt.haslayer(IP) else "?"

    # Recorre los mensajes concatenados en el segmento
    tipos = []
    # ¿StartupMessage/SSLRequest? (sin byte de tipo): primeros 4 bytes = length
    if tcp.dport == PG_PORT and len(payload) >= 8 and payload[0] == 0:
        import struct
        code = struct.unpack(">I", payload[4:8])[0]
        if code == 80877103:
            tipos.append("SSLRequest")
        elif code == 196608:
            tipos.append("StartupMessage(v3.0)")
    i = 0
    while i + 5 <= len(payload):
        t = payload[i]
        name = MSG.get(t)
        if name is None:
            break
        import struct
        (length,) = struct.unpack(">I", payload[i + 1:i + 5])
        tipos.append(name.split()[0])
        if length < 4:
            break
        i += 1 + length

    flag = ">" if tcp.dport == PG_PORT else "<"
    detalle = " ".join(tipos) if tipos else "(datos)"
    print("%s  %-21s -> %-21s  [%4d B]  %s" %
          (flag, src, dst, len(payload), detalle), flush=True)


def main():
    print("=== Sniffer Scapy - tráfico PostgreSQL (puerto %d, iface %s) ===" %
          (PG_PORT, IFACE))
    print("Genere tráfico con psql en otra terminal. Ctrl-C para terminar.\n")
    print("Dir  Origen                  Destino                Tam   Mensajes")
    print("-" * 78)
    try:
        sniff(iface=IFACE, filter="tcp port %d" % PG_PORT,
              prn=dissect, store=False, count=COUNT)
    except PermissionError:
        sys.exit("Sin permisos para sniffar. El contenedor scapy debe ser privileged/NET_RAW.")
    except KeyboardInterrupt:
        print("\n[sniffer] Detenido.")


if __name__ == "__main__":
    main()
