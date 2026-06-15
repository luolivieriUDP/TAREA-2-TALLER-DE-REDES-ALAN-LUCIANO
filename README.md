# Tarea 2 — Protocolo PostgreSQL

> Análisis del protocolo *wire* de PostgreSQL (frontend/backend v3.0, TCP 5432) usando la
> dupla **servidor `postgres` + cliente `psql`** en contenedores Docker, con captura y
> análisis del tráfico en Wireshark.

**Taller de Redes y Servicios · Universidad Diego Portales · 2026-1**

| | |
|---|---|
| **Integrantes** | Luciano Olivieri · Alan Troncoso |
| **Protocolo** | PostgreSQL frontend/backend v3.0 |
| **Software** | [postgres/postgres](https://github.com/postgres/postgres) (el mismo repositorio provee servidor y cliente) |
| **Profesor** | Diego Pineda — Sección 3 |

---

## Tabla de contenidos

1. [Descripción](#descripción)
2. [Requisitos](#requisitos)
3. [Puesta en marcha](#puesta-en-marcha)
4. [Uso: generar y capturar tráfico](#uso-generar-y-capturar-tráfico)
5. [Análisis de la captura](#análisis-de-la-captura)
6. [Resultados principales](#resultados-principales)
7. [Estructura del repositorio](#estructura-del-repositorio)
8. [Informe](#informe)
9. [Referencias](#referencias)

## Descripción

El escenario levanta **dos contenedores** cuyas imágenes se **construyen con Dockerfile** (no se
importa `postgres:17`); PostgreSQL se instala desde el repositorio oficial PGDG:

- **`psql-servidor`** — [docker/servidor/Dockerfile](docker/servidor/Dockerfile): Debian +
  `postgresql-17` + `tcpdump`. Su `entrypoint.sh` inicializa el cluster y crea la tabla
  `routers` con datos de ejemplo ([docker/init/01-esquema.sql](docker/init/01-esquema.sql)).
- **`psql-cliente`** — [docker/cliente/Dockerfile](docker/cliente/Dockerfile): Debian +
  `postgresql-client-17` (el binario `psql`).

El tráfico se captura con `tcpdump` **dentro del contenedor servidor** (la imagen lo incluye),
porque entre contenedores no es visible desde Wireshark en el host Windows; el resultado queda en
`captura/psql.pcap`. Cliente y servidor comparten una red *bridge* con IPs fijas (`172.18.0.2` y
`172.18.0.3`) y se resuelven por nombre. La autenticación es **SCRAM-SHA-256** y **no hay TLS**,
de modo que el protocolo queda legible en la captura — justo lo que el análisis necesita.

## Requisitos

- Windows 10/11 con **WSL2** y **Docker Desktop** (probado con 4.77.0, Engine 29.5.3).
- **Wireshark** (probado con 4.6.4) para abrir la captura.
- (Solo informe) **Overleaf** o un compilador LaTeX con pdfLaTeX.

## Puesta en marcha

```powershell
cd docker
# construye las imágenes desde Dockerfile y levanta servidor + cliente (sin docker-compose)
powershell -ExecutionPolicy Bypass -File construir-y-correr.ps1
docker ps                 # servidor (172.18.0.2) y cliente (172.18.0.3) en ejecución
```

> ⚠️ Al capturar se **sobrescribe `captura/psql.pcap`**. La captura usada en el informe está
> respaldada en `captura/respaldo/`.

## Uso: generar y capturar tráfico

```powershell
# 1) Iniciar la captura dentro del servidor
docker exec -u root -d psql-servidor tcpdump -i any -s 0 -w /capturas/psql.pcap tcp port 5432

# 2) Sesión interactiva del cliente hacia el servidor (contraseña: redes2025)
docker exec -it psql-cliente psql -h servidor -U taller -d tallerdb
```

Dentro de `psql`, por ejemplo:

```sql
SELECT * FROM routers;
INSERT INTO routers (nombre, ip) VALUES ('demo','10.0.5.5');
UPDATE routers SET activo = false WHERE nombre = 'edge-1';
SELECT count(*) FROM routers;
\q
```

```powershell
# 3) Detener la captura (cierra el .pcap) y limpiar
docker exec -u root psql-servidor pkill -INT tcpdump
docker rm -f psql-cliente psql-servidor
```

Las credenciales (`taller` / `redes2025`) son **de demostración** y existen solo para
reproducir el laboratorio.

## Análisis de la captura

- Abrir `captura/psql.pcap` en **Wireshark** y aplicar el filtro `pgsql`.
- Filtros útiles: `pgsql` · `tcp.port == 5432` · `pgsql.query` (solo consultas).
- Guía completa en [captura/INSTRUCCIONES-captura.md](captura/INSTRUCCIONES-captura.md);
  evidencia textual reproducible con `tshark` en
  [captura/analisis-tshark.txt](captura/analisis-tshark.txt).

## Resultados principales

Sobre la captura de referencia (65 frames, 3 conexiones, 7 consultas):

- Las 4 fases del protocolo observadas tal como las describe la documentación:
  negociación TLS → autenticación SCRAM-SHA-256 → 14×`ParameterStatus` + `BackendKeyData` +
  `ReadyForQuery` → pares `Query`/respuesta.
- **Sin TLS todo viaja en texto plano** (consultas y datos legibles en Wireshark);
  la contraseña es lo único que SCRAM nunca expone.
- Abrir una conexión costó **7,6 ms y 25 mensajes** de protocolo; responder una consulta,
  **0,53 ms** — la asimetría que justifica el *connection pooling*.

El detalle está en [captura/02-analisis-resultados.md](captura/02-analisis-resultados.md) y
en el informe.

## Estructura del repositorio

```
tarea2-psql/
├── README.md
├── docker/
│   ├── servidor/Dockerfile       # imagen del servidor (PostgreSQL + tcpdump, desde PGDG)
│   ├── servidor/entrypoint.sh    # init del cluster, rol, base y esquema
│   ├── cliente/Dockerfile        # imagen del cliente (psql, desde PGDG)
│   ├── construir-y-correr.ps1    # build + network + run (sin docker-compose)
│   └── init/01-esquema.sql       # tabla y datos de ejemplo
├── captura/
│   ├── psql.pcap                 # captura del tráfico (evidencia)
│   ├── respaldo/                 # copia de la captura usada en el informe
│   ├── INSTRUCCIONES-captura.md  # cómo capturar y analizar
│   ├── 02-analisis-resultados.md # análisis detallado (base del cap. 2)
│   └── analisis-tshark.txt       # evidencia textual verificable con tshark
├── informe/
│   ├── informe-tarea2.tex        # informe (capítulos 1 y 2), pdfLaTeX
│   ├── informe-tarea2.pdf        # PDF compilado
│   └── figuras/                  # logo, contenedores, conexión y capturas de Wireshark
└── docs/
    ├── 00-instalacion-docker.md  # instalación de WSL2 + Docker
    ├── 01-bitacora.md            # bitácora del trabajo
    └── 02-pendientes-y-guion.md  # pendientes y guion del video
```

## Informe

El informe ([informe/informe-tarea2.tex](informe/informe-tarea2.tex)) sigue la estructura del
*Informe Template* del curso y es **acumulativo**: esta entrega contiene los capítulos 1
(Introducción al protocolo) y 2 (Análisis de tráfico); el capítulo 3 se agrega en la Tarea 3.

Compila con **pdfLaTeX** (compilador por defecto de Overleaf): basta subir el `.tex` y la
carpeta `figuras/`. El PDF ya compilado (15 páginas) está incluido en el repositorio.

## Referencias

- [PostgreSQL: Frontend/Backend Protocol](https://www.postgresql.org/docs/17/protocol.html)
- [RFC 5802 — SCRAM](https://www.rfc-editor.org/rfc/rfc5802) ·
  [RFC 7677 — SCRAM-SHA-256](https://www.rfc-editor.org/rfc/rfc7677)
- [Repositorio APT oficial de PostgreSQL (PGDG)](https://www.postgresql.org/download/linux/debian/)
- [Disector PGSQL de Wireshark](https://www.wireshark.org/docs/dfref/p/pgsql.html)
- [Referencia de Dockerfile](https://docs.docker.com/reference/dockerfile/)
