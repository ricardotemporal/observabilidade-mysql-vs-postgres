#!/usr/bin/env python3
"""
analyze.py — Análise estatística dos resultados do experimento.

Produz:
1. Estatística descritiva (média, mediana, desvio-padrão, IC95%) por combinação
2. Testes de hipótese (H1, H2, H3)
3. Tabelas em markdown prontas pro documento
4. Arquivo de relatório completo em ../docs/analise.md

Uso:
    python3 analyze.py                          # usa ../results/results.csv
    python3 analyze.py --input outro.csv        # CSV customizado
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

SCRIPT_DIR = Path(__file__).parent
DEFAULT_CSV = SCRIPT_DIR.parent / "results" / "results.csv"
OUTPUT_MD = SCRIPT_DIR.parent / "docs" / "analise.md"


# -------------------- Helpers estatísticos --------------------

def mean_ci95(series: pd.Series) -> tuple[float, float, float]:
    """Retorna (média, limite inferior IC95%, limite superior IC95%)."""
    data = series.dropna().values
    n = len(data)
    if n < 2:
        mean = float(data[0]) if n == 1 else float("nan")
        return mean, mean, mean
    mean = float(np.mean(data))
    se = stats.sem(data)  # erro padrão
    # t de Student bicaudal com n-1 graus de liberdade
    h = se * stats.t.ppf(0.975, n - 1)
    return mean, mean - h, mean + h


def format_ci(mean: float, lo: float, hi: float, decimals: int = 2) -> str:
    """Formata 'média [lo, hi]' com precisão dada."""
    return f"{mean:.{decimals}f} [{lo:.{decimals}f}, {hi:.{decimals}f}]"


def cv_percent(series: pd.Series) -> float:
    """Coeficiente de variação em %."""
    data = series.dropna().values
    if len(data) < 2 or np.mean(data) == 0:
        return float("nan")
    return 100 * np.std(data, ddof=1) / np.mean(data)


# -------------------- Blocos de análise --------------------

def descriptive_table(df: pd.DataFrame) -> str:
    """Gera tabela descritiva com média, IC95%, desvio, CV% por combinação."""
    lines = []
    lines.append("## Tabela 1 — Estatística descritiva por combinação\n")
    lines.append("Cada linha = 3 réplicas. TPS e p95 com média e intervalo de confiança 95%.\n")
    lines.append("| DBMS | Workload | Threads | TPS média [IC95%] | p95 (ms) [IC95%] | CV TPS (%) |")
    lines.append("|---|---|---:|---|---|---:|")

    grouped = df.groupby(["dbms", "workload", "threads"], sort=False)
    for (dbms, workload, threads), group in grouped:
        tps_m, tps_lo, tps_hi = mean_ci95(group["tps"])
        p95_m, p95_lo, p95_hi = mean_ci95(group["latency_p95_ms"])
        cv = cv_percent(group["tps"])
        lines.append(
            f"| {dbms} | {workload} | {threads} | "
            f"{format_ci(tps_m, tps_lo, tps_hi)} | "
            f"{format_ci(p95_m, p95_lo, p95_hi)} | "
            f"{cv:.2f} |"
        )
    return "\n".join(lines) + "\n"


def resources_table(df: pd.DataFrame) -> str:
    """Tabela de uso de recursos (CPU e I/O)."""
    lines = []
    lines.append("## Tabela 2 — Uso de recursos por combinação (médias)\n")
    lines.append("| DBMS | Workload | Threads | CPU (%) | Escrita disco (MB/s) | Leitura disco (MB/s) |")
    lines.append("|---|---|---:|---:|---:|---:|")

    grouped = df.groupby(["dbms", "workload", "threads"], sort=False)
    for (dbms, workload, threads), group in grouped:
        cpu = group["cpu_percent_avg"].mean()
        wr_mb = group["disk_write_bytes_rate"].mean() / (1024 * 1024)
        rd_mb = group["disk_read_bytes_rate"].mean() / (1024 * 1024)
        lines.append(
            f"| {dbms} | {workload} | {threads} | "
            f"{cpu:.2f} | {wr_mb:.2f} | {rd_mb:.4f} |"
        )
    return "\n".join(lines) + "\n"


def hypothesis_h1(df: pd.DataFrame) -> str:
    """H1: Há diferença de TPS entre MySQL e PostgreSQL?"""
    lines = []
    lines.append("## H1 — Há diferença significativa de TPS entre MySQL e PostgreSQL?\n")
    lines.append("- **H₀:** μ(TPS_MySQL) = μ(TPS_Postgres)")
    lines.append("- **H₁:** μ(TPS_MySQL) ≠ μ(TPS_Postgres)")
    lines.append("- **α = 0,05**\n")

    # Pareamos por (workload, threads, replica) — comparação pareada
    pivot = df.pivot_table(
        index=["workload", "threads", "replica"],
        columns="dbms",
        values="tps",
    ).dropna()

    mysql_tps = pivot["mysql"].values
    pg_tps = pivot["postgres"].values

    # Teste de normalidade das diferenças (Shapiro-Wilk)
    diffs = pg_tps - mysql_tps
    shapiro_stat, shapiro_p = stats.shapiro(diffs)
    is_normal = shapiro_p > 0.05

    lines.append(f"Pares comparados: {len(pivot)} combinações (workload × threads × réplica).\n")
    lines.append(f"**Teste de normalidade das diferenças (Shapiro-Wilk):** "
                 f"W = {shapiro_stat:.4f}, p = {shapiro_p:.4f} → "
                 f"{'diferenças normais' if is_normal else 'diferenças NÃO normais'}.\n")

    if is_normal:
        t_stat, p_val = stats.ttest_rel(pg_tps, mysql_tps)
        test_name = "t de Student pareado"
    else:
        t_stat, p_val = stats.wilcoxon(pg_tps, mysql_tps)
        test_name = "Wilcoxon pareado"

    lines.append(f"**Teste aplicado:** {test_name}")
    lines.append(f"- Estatística: {t_stat:.4f}")
    lines.append(f"- p-valor: {p_val:.6f}")

    mean_mysql = np.mean(mysql_tps)
    mean_pg = np.mean(pg_tps)
    diff_pct = 100 * (mean_pg - mean_mysql) / mean_mysql

    lines.append(f"\n**Médias globais de TPS:**")
    lines.append(f"- MySQL: {mean_mysql:.2f}")
    lines.append(f"- PostgreSQL: {mean_pg:.2f}")
    lines.append(f"- Diferença: {diff_pct:+.2f}% (PostgreSQL em relação a MySQL)")

    if p_val < 0.05:
        lines.append(f"\n**Conclusão:** p = {p_val:.4f} < 0,05 → **rejeitamos H₀**. "
                     f"Há diferença estatisticamente significativa de TPS entre os dois SGBDs.")
    else:
        lines.append(f"\n**Conclusão:** p = {p_val:.4f} ≥ 0,05 → **não rejeitamos H₀**. "
                     f"Não há evidência estatística de diferença de TPS entre os dois SGBDs.")

    return "\n".join(lines) + "\n"


def hypothesis_h2(df: pd.DataFrame) -> str:
    """H2: Há interação entre SGBD e perfil de carga?"""
    lines = []
    lines.append("## H2 — O efeito do SGBD sobre TPS depende do perfil de carga?\n")
    lines.append("- **H₀:** não há interação entre DBMS e workload")
    lines.append("- **H₁:** há interação (efeito do DBMS varia entre workloads)")
    lines.append("- **α = 0,05**\n")

    # ANOVA fatorial de 2 fatores com interação
    try:
        from statsmodels.formula.api import ols
        from statsmodels.stats.anova import anova_lm

        model = ols("tps ~ C(dbms) * C(workload) + C(threads)", data=df).fit()
        table = anova_lm(model, typ=2)

        lines.append("**ANOVA (tipo II):**\n")
        lines.append("| Fator | Soma Sq | df | F | p-valor |")
        lines.append("|---|---:|---:|---:|---:|")
        for idx, row in table.iterrows():
            if idx == "Residual":
                lines.append(f"| {idx} | {row['sum_sq']:.2f} | {row['df']:.0f} | - | - |")
            else:
                lines.append(f"| {idx} | {row['sum_sq']:.2f} | {row['df']:.0f} | "
                             f"{row['F']:.4f} | {row['PR(>F)']:.6f} |")

        interaction_p = table.loc["C(dbms):C(workload)", "PR(>F)"]
        if interaction_p < 0.05:
            lines.append(f"\n**Conclusão:** p(interação) = {interaction_p:.4f} < 0,05 → "
                         f"**rejeitamos H₀**. A diferença de desempenho entre MySQL e "
                         f"PostgreSQL varia significativamente conforme o perfil de carga.")
        else:
            lines.append(f"\n**Conclusão:** p(interação) = {interaction_p:.4f} ≥ 0,05 → "
                         f"**não rejeitamos H₀**. Não há evidência de interação "
                         f"significativa entre SGBD e perfil de carga.")
    except ImportError:
        lines.append("**Aviso:** statsmodels não instalado. Pulando ANOVA formal.")
        # Análise visual alternativa: mostrar médias por combinação
        means = df.groupby(["dbms", "workload"])["tps"].mean().unstack()
        lines.append("\nMédias de TPS por DBMS × Workload:\n")
        lines.append(means.to_markdown())

    return "\n".join(lines) + "\n"


def hypothesis_h3(df: pd.DataFrame) -> str:
    """H3: Escalabilidade é linear entre 10 e 50 threads?"""
    lines = []
    lines.append("## H3 — A vazão escala linearmente com a concorrência (10 → 50 threads)?\n")
    lines.append("Escalabilidade linear ideal: 5× threads ⇒ 5× TPS.")
    lines.append("Calculamos o **fator de escalabilidade** observado = TPS(50) / TPS(10).")
    lines.append("Fator ideal = 5,00. Valores abaixo indicam saturação.\n")

    lines.append("| DBMS | Workload | TPS@10 | TPS@50 | Fator observado | Eficiência (% do ideal) |")
    lines.append("|---|---|---:|---:|---:|---:|")

    for (dbms, workload), group in df.groupby(["dbms", "workload"], sort=False):
        tps_10 = group[group["threads"] == 10]["tps"].mean()
        tps_50 = group[group["threads"] == 50]["tps"].mean()
        factor = tps_50 / tps_10 if tps_10 else float("nan")
        efficiency = 100 * factor / 5.0
        lines.append(f"| {dbms} | {workload} | {tps_10:.2f} | {tps_50:.2f} | "
                     f"{factor:.2f} | {efficiency:.1f}% |")

    lines.append("\n**Interpretação:** fatores << 5 indicam saturação (CPU, locks, I/O ou fila). "
                 "Em cenários OLTP em dataset pequeno cabendo em memória, a saturação tipicamente "
                 "ocorre por contenção de locks ou por CPU.")

    return "\n".join(lines) + "\n"


def summary_section(df: pd.DataFrame) -> str:
    """Resumo executivo com principais achados."""
    lines = []
    lines.append("# Relatório de Análise Estatística — Observabilidade MySQL vs PostgreSQL\n")
    lines.append(f"- **Total de execuções:** {len(df)}")
    lines.append(f"- **Combinações únicas:** {df.groupby(['dbms','workload','threads']).ngroups}")
    lines.append(f"- **Réplicas por combinação:** {df.groupby(['dbms','workload','threads']).size().iloc[0]}")
    lines.append(f"- **Taxa de erros observada:** "
                 f"{df['errors_per_sec'].fillna(0).mean():.4f} erros/s (média)")
    lines.append("")
    return "\n".join(lines)


# -------------------- Main --------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--output", type=Path, default=OUTPUT_MD)
    args = parser.parse_args()

    if not args.input.exists():
        raise FileNotFoundError(f"CSV não encontrado: {args.input}")

    df = pd.read_csv(args.input)
    print(f"Carregado: {len(df)} linhas de {args.input}")

    args.output.parent.mkdir(exist_ok=True)

    sections = [
        summary_section(df),
        descriptive_table(df),
        resources_table(df),
        hypothesis_h1(df),
        hypothesis_h2(df),
        hypothesis_h3(df),
    ]

    report = "\n".join(sections)
    args.output.write_text(report)

    print(f"\n✓ Relatório salvo em: {args.output}")
    print("\n" + "=" * 60)
    print(report)


if __name__ == "__main__":
    main()
