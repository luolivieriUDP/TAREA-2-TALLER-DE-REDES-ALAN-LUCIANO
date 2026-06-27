# ============================================================
# Contenedor Scapy / MITM - Tarea 3
# Incluye Scapy (última versión), tcpdump, nmap, netfilterqueue,
# iproute2 (tc netem), iptables y las librerías de análisis.
# ============================================================
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        tcpdump nmap netcat-traditional iproute2 \
        iputils-ping procps libpcap-dev build-essential \
        iptables python3-dev postgresql-client \
        libnetfilter-queue-dev libnfnetlink-dev \
 && rm -rf /var/lib/apt/lists/*

# Paquetes esenciales para los scripts (proxy/fuzzing/mods/sniffer/plots)
RUN pip install --no-cache-dir scapy \
        psycopg2-binary matplotlib pandas numpy
# netfilterqueue es opcional (no lo usan los scripts entregados); su extensión C
# puede no compilar en algunos entornos, así que su instalación es no-fatal.
RUN pip install --no-cache-dir netfilterqueue || \
        echo "[aviso] netfilterqueue no se instaló (opcional, no requerido)."

WORKDIR /scripts
CMD ["/bin/bash"]
