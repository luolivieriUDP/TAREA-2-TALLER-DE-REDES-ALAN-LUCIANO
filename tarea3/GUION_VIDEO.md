# Guión de Video — Tarea 3 (PostgreSQL · Scapy MITM)

**Duración objetivo: 6–8 minutos** (el enunciado exige *no menos de 6 y no más de 8*).
Estudiantes: Luciano Olivieri · Alan Troncoso — Taller de Redes y Servicios, UDP.

---

## Setup de grabación

- **Resolución:** 1920×1080 mínimo.
- **Layout:** 2 terminales lado a lado.
  - *Terminal izquierda:* servidor / proxy / logs.
  - *Terminal derecha:* cliente / scapy / ejecución de scripts.
- **Fuente del terminal:** mínimo 14 px (legible en video).
- **Grabación:** OBS Studio (Win/Linux/Mac) o `simplescreenrecorder` (Linux).
- **Antes de grabar:** `docker compose up -d --build` y verificar `docker compose ps`.
- **Audio:** narrar cada paso explicando *qué* se modifica y *qué* repercusión tiene.

---

## Guión con timestamps

### [0:00–0:30] Introducción
- Decir nombre(s), curso **"Taller de Redes y Servicios — UDP"**, **Tarea 3**.
- Mencionar: "continuamos con el protocolo PostgreSQL de la Tarea 2; ahora
  inyectamos y modificamos tráfico con un proxy MITM y Scapy".
- Ejecutar y mostrar los 3 contenedores corriendo:
  ```bash
  docker compose ps
  ```

### [0:30–1:30] Fuzzing 1 — Payload aleatorio
- Ejecutar:
  ```bash
  docker exec scapy_mitm python3 /scripts/fuzzing_1.py
  ```
- Mostrar las 10 iteraciones de bytes aleatorios y la columna **CLASIFICACIÓN**.
- Narrar: *"el servidor rechaza y cierra cada conexión porque el campo length
  aleatorio supera el máximo del startup packet, pero **sigue vivo** tras las 10
  iteraciones"*. Señalar la línea final "SOBREVIVIÓ".

### [1:30–2:30] Fuzzing 2 — Startup message mutado
- Ejecutar:
  ```bash
  docker exec scapy_mitm python3 /scripts/fuzzing_2.py
  ```
- Mostrar al menos **3 casos** y leer su respuesta real:
  - **Caso 1** (protocol 99.0): `FATAL ... unsupported frontend protocol 99.0`.
  - **Caso 2** (`length 0xFFFFFFFF`): el servidor cierra la conexión.
  - **Caso 7** (solo 4 bytes): **timeout**, el backend queda esperando más bytes.
- Narrar la diferencia con el Fuzzing 1: *"aquí cada mutación gatilla una reacción
  distinta; el servidor valida por capas: tamaño, versión y estructura"*.

### [2:30–3:30] Modificación 1 — Byte de tipo de mensaje
- Ejecutar (modo automático, muestra los 3 casos):
  ```bash
  docker exec scapy_mitm python3 /scripts/mod_1_message_type.py
  ```
- Señalar la línea `[hook] 'Q' (0x51) -> 0x..` y la respuesta del servidor:
  - **A** (`Q→X`): la conexión **se cierra** limpiamente (Terminate).
  - **B** (`Q→0xFF`): `FATAL invalid frontend message type 255`.
  - **C** (`Q→p`): `FATAL invalid frontend message type 112`.
- Narrar: *"cambiar un solo byte rompe la sincronía del protocolo"*.

### [3:30–4:30] Modificación 2 — Campo length
- Ejecutar:
  ```bash
  docker exec scapy_mitm python3 /scripts/mod_2_length.py
  ```
- Mostrar el **Caso A** (`length+1000`): el cliente queda **bloqueado** y aborta por
  **timeout** a los 4 s (el backend espera bytes que nunca llegan). Esperar y mostrar
  el timeout en pantalla.
- Mostrar Caso B (`invalid string in message`) y Caso C (cierre por `invalid message
  length`). Recalcar: *"el servidor nunca se cae; cada sesión es un proceso aparte"*.

### [4:30–5:30] Modificación 3 — Contenido SQL (el ataque clave)
- **Opción recomendada: demo en vivo** para que se vea la latencia real.
  - Terminal izquierda (proxy, caso A `pg_sleep`):
    ```bash
    docker exec -it -e MITM_AUTO=0 -e MITM_CASE=A scapy_mitm \
        python3 /scripts/mod_3_query.py
    ```
  - Terminal derecha (cliente a través del proxy, puerto 5433):
    ```bash
    docker exec -it psql-cliente psql -h scapy_mitm -p 5433 -U taller -d tallerdb
    tallerdb=> \timing on
    tallerdb=> SELECT 1;
    ```
  - Mostrar que `SELECT 1` **tarda ~5 segundos** (el servidor ejecuta `pg_sleep(5)`),
    y en la terminal izquierda se ve el hook reescribiendo el SQL.
- (Opcional) Ejecutar el modo automático para mostrar también los casos B
  (`42P01 relation does not exist`) y C (`SELECT 0`, resultado vaciado):
  ```bash
  docker exec scapy_mitm python3 /scripts/mod_3_query.py
  ```
- Narrar: *"sin TLS, un MITM reescribe la consulta y ni cliente ni servidor lo notan:
  el protocolo no tiene integridad de mensaje"*.

### [5:30–6:30] Métricas de red y cotas de desempeño
- Aplicar latencia y mostrar su efecto:
  ```bash
  docker exec -u root scapy_mitm tc qdisc add dev eth0 root netem delay 500ms
  docker exec -it psql-cliente bash -c "PGPASSWORD=tallerpass psql -h servidor -U taller -d tallerdb -c 'SELECT 1;'"
  docker exec -u root scapy_mitm tc qdisc del dev eth0 root
  ```
  (o ejecutar `bash /metrics/metric1_latency.sh`).
- Abrir los gráficos generados y **señalar la línea de cota de desempeño**:
  - `grafico_latencia.png` → **cota = 100 ms**.
  - `grafico_perdida.png` → **cota = 30 %**.
- Narrar el significado: *"hasta 100 ms el servicio es estable; más allá, el throughput
  cae bajo el umbral operacional. En pérdida, hasta 30 % aún es usable; a 50 % colapsa
  a 1,7 consultas/seg (gracias a TCP la conexión no se rompe, pero queda inservible)"*.

### [6:30–7:30] Mostrar el informe PDF
- Abrir `informe/informe_tarea3.pdf`.
- Pasar páginas mostrando: portada, índice, tablas de fuzzing, los **outputs reales**
  de cada modificación, las tablas de métricas y los dos gráficos.
- Señalar las secciones de **fundamentación** (comportamiento esperado vs observado).

### [7:30–8:00] Conclusiones orales
- *"El protocolo PostgreSQL sin TLS no tiene integridad de mensaje."*
- *"Un atacante MITM puede modificar consultas arbitrariamente sin ser detectado."*
- *"El servidor es robusto ante inputs malformados: responde con errores FATAL o
  cierra, pero no se cae."*
- *"Las cotas de desempeño fueron 100 ms de latencia y 30 % de pérdida de paquetes."*
- Cierre y agradecimiento.

---

## Comandos para subir al MISMO GitLab de la Tarea 2

```bash
cd /ruta/al/repo/tarea2          # el repositorio GitLab de la Tarea 2
cp -r /ruta/a/tarea3 .           # copiar la carpeta tarea3/ dentro del repo
git add tarea3/
git commit -m "feat: Tarea 3 — Scapy MITM, fuzzing, modificaciones y metricas"
git push origin main
```

## Subir el video

- **YouTube:** Crear → Subir video → Visibilidad **"No listado"** (o público) → copiar URL.
- **O GitLab:** subir el archivo de video al repositorio (o enlazar en el README).
- Pegar la URL en `tarea3/README.md` (sección 🎥 Video) y en el README principal del repo.

## Entrega en Canvas

- Subir el PDF del informe (`informe_tarea3.pdf`).
- En el comentario de entrega, incluir el **link al repositorio GitLab** (y al video).
