-- ============================================================
-- Esquema inicial de la base tallerdb (Tarea 2)
-- Tabla routers con 4 filas de prueba.
-- ============================================================
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
