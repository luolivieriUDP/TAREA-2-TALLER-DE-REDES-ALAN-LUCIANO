# Tarea 3 — Inyección y Modificación de Tráfico con Scapy (PostgreSQL)

**Taller de Redes y Servicios — Universidad Diego Portales**
Estudiantes: Luciano Olivieri · Alan Troncoso — Profesor: Diego Pineda — Sección 3

Esta tarea continúa la Tarea 2 (análisis del protocolo *PostgreSQL Frontend/Backend
Wire Protocol*). Aquí se intercepta el tráfico cliente/servidor con un **proxy MITM**,
se **inyecta** tráfico con técnicas de *fuzzing*, se **modifican** campos del protocolo
en tiempo real y se miden **cotas de desempeño** ante latencia y pérdida de paquetes.

---

## 🎥 Video (entregable)

> **Link del video (PÚBLICO):** https://youtu.be/YppxUeWYZHc
>
> *(El enunciado exige video **público** de 6 a 8 min. Pegar aquí la URL de
> YouTube. Ver guión paso a paso en [`GUION_VIDEO.md`](GUION_VIDEO.md).)*

---

## Estructura del repositorio

```
tarea3/
├── docker-compose.yml        # servidor + cliente (Tarea 2) + scapy (nuevo)
├── .env.example              # credenciales y topología (copiar a .env)
├── tarea2/                   # entorno PostgreSQL recreado desde el informe T2
│   ├── servidor/Dockerfile + entrypoint.sh
│   ├── cliente/Dockerfile
│   └── init/01-esquema.sql   # tabla routers con 4 filas
├── scapy/
│   ├── Dockerfile            # Scapy + tcpdump + tc + netfilterqueue + ...
│   ├── requirements.txt
│   ├── mitm_proxy.py         # proxy TCP MITM base (con hooks)
│   ├── sniffer_scapy.py      # interceptación/disección pasiva con Scapy
│   ├── pg_client.py          # cliente PG mínimo con SCRAM (driver de pruebas)
│   ├── fuzzing_1.py          # Fuzzing 1: payload aleatorio (dumb fuzzing)
│   ├── fuzzing_2.py          # Fuzzing 2: startup mutado + bit-flipping
│   ├── mod_1_message_type.py # Modificación 1: byte de tipo de mensaje
│   ├── mod_2_length.py       # Modificación 2: campo length
│   └── mod_3_query.py        # Modificación 3: contenido SQL
├── metrics/
│   ├── metric1_latency.sh    # Métrica 1: latencia con tc netem (Docker)
│   ├── metric2_loss.sh       # Métrica 2: pérdida con tc netem (Docker)
│   ├── generate_metrics_local.py  # genera CSVs (latencia real + modelo pérdida)
│   ├── plot_metrics.py       # gráficos métrica vs throughput
│   ├── metric1_results.csv / metric2_results.csv
│   └── grafico_latencia.png / grafico_perdida.png
├── capturas/                 # salidas reales de cada experimento (.txt)
├── informe/
│   ├── informe_tarea3.tex / .pdf
│   ├── referencias.bib
│   └── imagenes/             # gráficos para el informe
├── GUION_VIDEO.md            # guión de grabación con timestamps
└── README.md
```

---

## Configuración (Fase 0)

| Componente | Valor |
|---|---|
| Servidor | contenedor `psql-servidor`, IP `172.18.0.2`, hostname `servidor` |
| Cliente  | contenedor `psql-cliente`, IP `172.18.0.3` |
| Scapy/MITM | contenedor `scapy_mitm`, IP `172.18.0.4` (privileged) |
| Red | `redpsql` (bridge, `172.18.0.0/16`) |
| Puerto PostgreSQL | `5432` · Proxy MITM: `5433` |
| Usuario / Base | `taller` / `tallerdb` |
| Password | `tallerpass` *(definida aquí; SCRAM nunca la expone en el informe T2)* |
| Auth | `scram-sha-256` · PostgreSQL 17 |

> Todas las credenciales y nombres están en [`.env.example`](.env.example) y son
> editables en la cabecera de cada script (`SERVER_HOST`, `PG_PORT`, etc.).

---

## Cómo levantar el entorno completo (desde cero)

```bash
cd tarea3
cp .env.example .env                 # opcional: ajustar credenciales
docker compose up -d --build         # construye y levanta los 3 contenedores
docker compose ps                    # verificar que están "Up"
```

**Validaciones del contenedor scapy:**
```bash
docker exec scapy_mitm python3 -c "from scapy.all import *; print('Scapy OK')"
docker exec scapy_mitm tc -V
docker exec scapy_mitm tcpdump --version
```

**Probar la conexión cliente → servidor (como en Tarea 2):**
```bash
docker exec -it psql-cliente psql -h servidor -U taller -d tallerdb
# password: tallerpass  ->  SELECT * FROM routers;
```

---

## Ejecutar los experimentos

Todos los scripts se ejecutan **dentro del contenedor scapy** y guardan su salida en
`capturas/`. Variables (`SERVER_HOST`, `PG_PORT`, `PROXY_PORT`, `PG_USER`,
`PG_PASSWORD`, `PG_DB`) ya vienen del `docker-compose.yml`.

### Interceptación con Scapy (sniffing pasivo)
```bash
# Terminal 1: sniffer Scapy disecando el protocolo
docker exec -it scapy_mitm python3 /scripts/sniffer_scapy.py
# Terminal 2: generar tráfico
docker exec -it psql-cliente psql -h servidor -U taller -d tallerdb -c "SELECT * FROM routers;"
```

### Fuzzing (2 técnicas distintas)
```bash
docker exec scapy_mitm python3 /scripts/fuzzing_1.py   # payload aleatorio
docker exec scapy_mitm python3 /scripts/fuzzing_2.py   # startup mutado + bit-flip
```

### Modificaciones (3) — modo automático
Cada script levanta el proxy MITM y un cliente interno que envía la consulta a
través de él, mostrando la respuesta real del servidor para los 3 casos (A/B/C):
```bash
docker exec scapy_mitm python3 /scripts/mod_1_message_type.py
docker exec scapy_mitm python3 /scripts/mod_2_length.py
docker exec scapy_mitm python3 /scripts/mod_3_query.py
```

### Modificaciones — modo DEMO en vivo (para el video)
Lanza el proxy con un caso activo y conéctate con `psql` real desde el cliente:
```bash
# Terminal 1 (proxy con el caso A activo):
docker exec -it -e MITM_AUTO=0 -e MITM_CASE=A scapy_mitm python3 /scripts/mod_3_query.py
# Terminal 2 (cliente a través del proxy en el puerto 5433):
docker exec -it psql-cliente psql -h scapy_mitm -p 5433 -U taller -d tallerdb
tallerdb=> SELECT 1;        # ¡tarda 5 s por pg_sleep!
```

### Métricas (latencia y pérdida)
```bash
# Requieren tc netem (Linux). Si el cliente no tiene NET_ADMIN, usar el scapy:
docker exec scapy_mitm bash /metrics/metric1_latency.sh   # NETEM_CONTAINER=scapy_mitm
docker exec scapy_mitm bash /metrics/metric2_loss.sh
# Generar gráficos:
docker exec scapy_mitm python3 /metrics/plot_metrics.py
```

---

## Compilar el informe

```bash
cd informe
pdflatex -interaction=nonstopmode informe_tarea3.tex
pdflatex -interaction=nonstopmode informe_tarea3.tex   # 2ª pasada (índice/refs)
```
Sin LaTeX local, con Docker:
```bash
docker run --rm -v "$(pwd)":/work -w /work texlive/texlive:latest \
    sh -c "pdflatex -interaction=nonstopmode informe_tarea3.tex && \
           pdflatex -interaction=nonstopmode informe_tarea3.tex"
```

---

## Nota sobre la reproducción de las salidas incluidas

Todas las salidas de `capturas/` y los CSV de métricas se generaron ejecutando los
scripts en el **entorno Docker real** (los 3 contenedores sobre la red `redpsql`,
PostgreSQL 17 con rol `taller`, base `tallerdb`, tabla `routers` y autenticación
SCRAM-SHA-256). Por eso los encabezados muestran `servidor:5432`. Las dos métricas
(latencia y pérdida) se midieron con **`tc qdisc netem` real** aplicado sobre la
interfaz `eth0` del contenedor cliente. Para regenerar todo desde cero:

```bash
docker compose up -d --build
docker exec scapy_mitm python3 /scripts/fuzzing_1.py
docker exec scapy_mitm python3 /scripts/fuzzing_2.py
docker exec scapy_mitm python3 /scripts/mod_1_message_type.py
docker exec scapy_mitm python3 /scripts/mod_2_length.py
docker exec scapy_mitm python3 /scripts/mod_3_query.py
bash metrics/metric1_latency.sh      # desde el host (orquesta docker exec)
bash metrics/metric2_loss.sh
python metrics/plot_metrics.py
```
