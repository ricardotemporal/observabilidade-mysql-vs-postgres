#!/usr/bin/env python3
"""
plots.py — Gera os gráficos do experimento.

Produz (em ../docs/figures/):
1. tps_by_workload.png         — barras TPS por DBMS × workload (com IC95%)
2. p95_by_workload.png         — barras latência p95 por DBMS × workload
3. boxplot_tps.png             — boxplots TPS por combinação
4. scalability.png             — TPS vs threads por DBMS e workload
5. resources_heatmap.png       — CPU% por combinação

Uso:
    python3 plots.py
"""

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

SCRIPT_DIR = Path(__file__).parent
DEFAULT_CSV = SCRIPT_DIR.parent / "results" / "results.csv"
FIGURES_DIR = SCRIPT_DIR.parent / "docs" / "figures"

# Paleta simples e acessível
COLOR_MYSQL = "#00758F"   # azul petróleo (cor oficial MySQL)
COLOR_PG = "#E87722"      # laranja queimado (contraste claro contra MySQL)
PALETTE = {"mysql": COLOR_MYSQL, "postgres": COLOR_PG}

plt.rcParams.update({
    "font.size": 11,
    "axes.titlesize": 12,
    "axes.labelsize": 11,
    "figure.dpi": 100,
    "savefig.dpi": 150,
    "savefig.bbox": "tight",
})


def ci95(series: pd.Series) -> tuple[float, float]:
    """Retorna (média, half-width do IC95%) para barra de erro."""
    data = series.dropna().values
    n = len(data)
    if n < 2:
        return (float(data[0]) if n == 1 else float("nan"), 0.0)
    mean = np.mean(data)
    se = stats.sem(data)
    h = se * stats.t.ppf(0.975, n - 1)
    return mean, h


def plot_bars_with_ci(df: pd.DataFrame, metric: str, ylabel: str,
                      title: str, outfile: Path):
    """Barras agrupadas: x = workload, hue = dbms, com barras de erro IC95%."""
    workloads = sorted(df["workload"].unique())
    dbms_list = sorted(df["dbms"].unique())

    x = np.arange(len(workloads))
    width = 0.35

    fig, ax = plt.subplots(figsize=(9, 5))
    for i, dbms in enumerate(dbms_list):
        means = []
        errs = []
        for wl in workloads:
            sub = df[(df["dbms"] == dbms) & (df["workload"] == wl)]
            # Agrega todas threads + réplicas
            m, h = ci95(sub[metric])
            means.append(m)
            errs.append(h)
        offset = (i - (len(dbms_list) - 1) / 2) * width
        ax.bar(x + offset, means, width, yerr=errs, capsize=4,
               label=dbms, color=PALETTE.get(dbms, None), alpha=0.85,
               edgecolor="black", linewidth=0.6)

    ax.set_xticks(x)
    ax.set_xticklabels([w.replace("oltp_", "") for w in workloads])
    ax.set_xlabel("Perfil de carga")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend(title="SGBD")
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    ax.set_axisbelow(True)

    fig.savefig(outfile)
    plt.close(fig)
    print(f"  ✓ {outfile.name}")


def plot_boxplot(df: pd.DataFrame, outfile: Path):
    """Boxplot de TPS por combinação dbms × workload × threads."""
    df = df.copy()
    df["cenario"] = (df["dbms"] + "\n" + df["workload"].str.replace("oltp_", "")
                     + "\nT=" + df["threads"].astype(str))

    # Ordena: agrupa por dbms primeiro
    order = (df.groupby("cenario")["dbms"].first()
               .sort_values()
               .index.tolist())
    data = [df[df["cenario"] == c]["tps"].values for c in order]
    colors = [PALETTE[df[df["cenario"] == c]["dbms"].iloc[0]] for c in order]

    fig, ax = plt.subplots(figsize=(13, 6))
    bp = ax.boxplot(data, patch_artist=True, tick_labels=order,
                    widths=0.6, showmeans=True,
                    meanprops={"marker": "D", "markerfacecolor": "white",
                               "markeredgecolor": "black", "markersize": 6})
    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.75)

    ax.set_ylabel("TPS (transações/segundo)")
    ax.set_title("Distribuição de TPS por cenário (3 réplicas cada)")
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    ax.set_axisbelow(True)
    plt.setp(ax.get_xticklabels(), fontsize=9)

    fig.savefig(outfile)
    plt.close(fig)
    print(f"  ✓ {outfile.name}")


def plot_scalability(df: pd.DataFrame, outfile: Path):
    """TPS vs threads, uma linha por (dbms, workload)."""
    fig, ax = plt.subplots(figsize=(9, 5.5))

    linestyles = {"oltp_read_only": "-", "oltp_write_only": "--",
                  "oltp_read_write": "-."}
    markers = {"oltp_read_only": "o", "oltp_write_only": "s",
               "oltp_read_write": "^"}

    for dbms in sorted(df["dbms"].unique()):
        for wl in sorted(df["workload"].unique()):
            sub = df[(df["dbms"] == dbms) & (df["workload"] == wl)]
            thread_vals = sorted(sub["threads"].unique())
            means = [sub[sub["threads"] == t]["tps"].mean() for t in thread_vals]
            errs = [ci95(sub[sub["threads"] == t]["tps"])[1] for t in thread_vals]

            label = f"{dbms} · {wl.replace('oltp_', '')}"
            ax.errorbar(thread_vals, means, yerr=errs, capsize=4,
                        linestyle=linestyles[wl], marker=markers[wl],
                        markersize=8, label=label,
                        color=PALETTE[dbms], linewidth=1.8)

    ax.set_xlabel("Número de threads (concorrência)")
    ax.set_ylabel("TPS (transações/segundo)")
    ax.set_title("Escalabilidade: TPS vs concorrência")
    ax.legend(loc="best", fontsize=9)
    ax.grid(True, linestyle="--", alpha=0.4)
    ax.set_axisbelow(True)

    fig.savefig(outfile)
    plt.close(fig)
    print(f"  ✓ {outfile.name}")


def plot_resources_heatmap(df: pd.DataFrame, outfile: Path):
    """Heatmap de CPU% por combinação."""
    pivot = (df.groupby(["dbms", "workload", "threads"])["cpu_percent_avg"]
               .mean()
               .unstack("threads"))
    pivot.index = [f"{d} · {w.replace('oltp_', '')}" for d, w in pivot.index]

    fig, ax = plt.subplots(figsize=(7, 5))
    im = ax.imshow(pivot.values, aspect="auto", cmap="YlOrRd")
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels(pivot.columns)
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index)
    ax.set_xlabel("Threads")
    ax.set_title("Uso médio de CPU (%) por cenário")

    # Anotar valores nas células
    for i in range(pivot.shape[0]):
        for j in range(pivot.shape[1]):
            val = pivot.values[i, j]
            ax.text(j, i, f"{val:.1f}", ha="center", va="center",
                    color="black" if val < pivot.values.max() * 0.6 else "white",
                    fontsize=10, fontweight="bold")

    fig.colorbar(im, ax=ax, label="CPU (%)")
    fig.savefig(outfile)
    plt.close(fig)
    print(f"  ✓ {outfile.name}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--outdir", type=Path, default=FIGURES_DIR)
    args = parser.parse_args()

    if not args.input.exists():
        raise FileNotFoundError(f"CSV não encontrado: {args.input}")

    df = pd.read_csv(args.input)
    print(f"Carregado: {len(df)} linhas de {args.input}")

    args.outdir.mkdir(parents=True, exist_ok=True)
    print(f"\nGerando gráficos em {args.outdir}/:\n")

    plot_bars_with_ci(df, "tps", "TPS médio (transações/s)",
                      "TPS por SGBD e perfil de carga (com IC 95%)",
                      args.outdir / "tps_by_workload.png")

    plot_bars_with_ci(df, "latency_p95_ms", "Latência p95 (ms)",
                      "Latência p95 por SGBD e perfil de carga (com IC 95%)",
                      args.outdir / "p95_by_workload.png")

    plot_boxplot(df, args.outdir / "boxplot_tps.png")
    plot_scalability(df, args.outdir / "scalability.png")
    plot_resources_heatmap(df, args.outdir / "resources_heatmap.png")

    print(f"\n✓ Concluído — {5} gráficos gerados.")


if __name__ == "__main__":
    main()
