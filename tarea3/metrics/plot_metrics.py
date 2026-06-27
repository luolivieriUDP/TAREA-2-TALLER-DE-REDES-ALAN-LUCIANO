#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================================
 plot_metrics.py  -  Gráficos métrica vs throughput
 Tarea 3 - Taller de Redes y Servicios (UDP)
----------------------------------------------------------------------------
 Genera dos gráficos de barras (latencia y pérdida) a partir de los CSV de
 resultados, marcando la cota de desempeño con una línea vertical.
   - Barras azules  (#2563eb): conexión estable (status 'ok')
   - Barras rojas   (#dc2626): conexión degradada/rota ('degradado'/'error')
   - Línea naranja punteada en la cota de desempeño (último valor 'ok')
 Copia los PNG a ../informe/imagenes/.
============================================================================
"""
import os
import shutil
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.lines import Line2D

HERE = os.path.dirname(os.path.abspath(__file__))
IMG_DIR = os.path.join(HERE, "..", "informe", "imagenes")

COLOR_OK   = "#2563eb"
COLOR_BAD  = "#dc2626"
COLOR_COTA = "#f59e0b"

# Umbral operacional: por debajo de OPS_MIN consultas/seg por conexión el
# servicio se considera degradado para una carga interactiva/OLTP. Los CSV
# guardan la medición cruda (status 'ok' = completó sin error); aquí se aplica
# el umbral para identificar la cota de desempeño.
OPS_MIN = 5.0


def eff_status(raw_status, throughput):
    if raw_status == "error" or throughput <= 0:
        return "error"
    if throughput < OPS_MIN:
        return "degradado"
    return "ok"


def make_plot(csv_path, xcol, xlabel, unit, title, out_png):
    df = pd.read_csv(csv_path)
    x = df[xcol].astype(int).tolist()
    y = df["throughput_ops_sec"].astype(float).tolist()
    raw_status = df["status"].tolist()
    status = [eff_status(s, v) for s, v in zip(raw_status, y)]

    colors = [COLOR_OK if s == "ok" else COLOR_BAD for s in status]
    labels = ["%d" % v for v in x]
    positions = list(range(len(x)))

    # Cota de desempeño = último valor con status efectivo 'ok'
    ok_idx = [i for i, s in enumerate(status) if s == "ok"]
    cota_idx = ok_idx[-1] if ok_idx else -1
    cota_val = x[cota_idx] if cota_idx >= 0 else None

    # Escala logarítmica: el throughput abarca varios órdenes de magnitud
    # (de miles de ops/s sin degradación a ~1 ops/s). El valor 0 (ruptura de
    # la conexión) se dibuja al piso del eje y se anota como "ruptura".
    floor = 0.5
    heights = [v if v > 0 else floor for v in y]

    fig, ax = plt.subplots(figsize=(10, 6))
    bars = ax.bar(positions, heights, color=colors, width=0.62,
                  edgecolor="white", linewidth=0.6, zorder=3)
    # Sombrear con trama las barras de ruptura (throughput = 0)
    for b, val in zip(bars, y):
        if val <= 0:
            b.set_hatch("///")

    ax.set_yscale("log")
    ax.set_ylim(floor, max(heights) * 2.2)

    # Anotación del throughput real encima de cada barra
    for b, val in zip(bars, y):
        if val <= 0:
            txt = "ruptura"
        elif val < 100:
            txt = "%.1f" % val
        else:
            txt = "%.0f" % val
        ax.text(b.get_x() + b.get_width() / 2, b.get_height() * 1.08,
                txt, ha="center", va="bottom", fontsize=9,
                color="#111827", zorder=4)

    # Línea vertical de cota de desempeño (entre la última 'ok' y la siguiente)
    cota_legend = None
    if cota_idx >= 0 and cota_idx < len(x) - 1:
        line_x = cota_idx + 0.5
        ax.axvline(line_x, color=COLOR_COTA, linestyle="--", linewidth=2.2,
                   zorder=5)
        cota_legend = "Cota de desempeño: %d %s" % (cota_val, unit)
    elif cota_idx == len(x) - 1:
        cota_legend = "Cota de desempeño: > %d %s (sin ruptura observada)" % (cota_val, unit)

    ax.set_xticks(positions)
    ax.set_xticklabels(labels)
    ax.set_xlabel(xlabel, fontsize=12)
    ax.set_ylabel("Throughput (consultas/segundo)", fontsize=12)
    ax.set_title(title, fontsize=13, fontweight="bold", pad=14)

    # Estética: sin spines superior/derecho, grid horizontal sutil
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.yaxis.grid(True, alpha=0.4, zorder=0)
    ax.set_axisbelow(True)
    ax.margins(y=0.12)

    legend_items = [
        Patch(facecolor=COLOR_OK, label="Conexión estable"),
        Patch(facecolor=COLOR_BAD, label="Conexión degradada/rota"),
    ]
    if cota_legend:
        legend_items.append(Line2D([0], [0], color=COLOR_COTA, linestyle="--",
                                   linewidth=2.2, label=cota_legend))
    ax.legend(handles=legend_items, fontsize=10, framealpha=0.95,
              loc="upper right")

    fig.savefig(out_png, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("   %s  ->  cota de desempeño = %s %s" %
          (os.path.basename(out_png),
           cota_val if cota_val is not None else "n/d", unit))
    return cota_val


def main():
    print("=== Generando gráficos métrica vs throughput ===")
    cota_lat = make_plot(
        os.path.join(HERE, "metric1_results.csv"),
        "delay_ms", "Latencia inyectada (ms)", "ms",
        "Métrica 1 — Latencia vs Throughput (PostgreSQL)",
        os.path.join(HERE, "grafico_latencia.png"))

    cota_loss = make_plot(
        os.path.join(HERE, "metric2_results.csv"),
        "loss_pct", "Pérdida de paquetes (%)", "%",
        "Métrica 2 — Pérdida de paquetes vs Throughput (PostgreSQL)",
        os.path.join(HERE, "grafico_perdida.png"))

    # Copiar a informe/imagenes/
    os.makedirs(IMG_DIR, exist_ok=True)
    for png in ("grafico_latencia.png", "grafico_perdida.png"):
        shutil.copy(os.path.join(HERE, png), os.path.join(IMG_DIR, png))
    print("   PNGs copiados a informe/imagenes/")

    print("\n=== COTAS DE DESEMPEÑO IDENTIFICADAS ===")
    print("   Métrica 1 (latencia): %s ms" % cota_lat)
    print("   Métrica 2 (pérdida) : %s %%" % cota_loss)


if __name__ == "__main__":
    main()
