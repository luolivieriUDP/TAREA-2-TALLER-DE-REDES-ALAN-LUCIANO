-- 01-esquema.sql
-- Se ejecuta UNA vez al crear el contenedor del servidor (docker-entrypoint-initdb.d).
-- Crea una tabla con datos para que las consultas del cliente generen tráfico de protocolo
-- con mensajes RowDescription + DataRow (filas de respuesta) fáciles de ver en Wireshark.

CREATE TABLE routers (
    id      SERIAL PRIMARY KEY,
    nombre  TEXT    NOT NULL,
    ip      INET    NOT NULL,
    activo  BOOLEAN DEFAULT true
);

INSERT INTO routers (nombre, ip, activo) VALUES
    ('core-1',   '10.0.0.1',  true),
    ('border-1', '10.0.0.2',  true),
    ('edge-1',   '10.0.1.10', false),
    ('edge-2',   '10.0.1.11', true);

-- Consultas sugeridas para la demo / captura:
--   SELECT * FROM routers;
--   SELECT nombre, ip FROM routers WHERE activo = true;
--   INSERT INTO routers (nombre, ip) VALUES ('test-1', '10.0.9.9');
--   UPDATE routers SET activo = false WHERE nombre = 'edge-2';
