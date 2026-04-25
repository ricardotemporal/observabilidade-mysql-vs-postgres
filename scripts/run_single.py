#!/usr/bin/env python3
"""
run_single.py — Executa UMA combinação de benchmark.

Uso:
    python3 run_single.py --dbms mysql --workload oltp_read_write --threads 50 --replica 1

Faz:
1. Prepara dataset (se --skip-prepare não for passado).
2. Warmup de 60s.
3. Medição de 180s com sysbench.
4. Coleta métricas do Prometheus na janela de medição.
5. Salva CSV em ../results/.

Premissas:
- Containers do docker-compose já estão UP.
- sysbench instalado no host (WSL).
"""

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

# -------------------- Config --------------------
PROMETHEUS_URL = "http://localhost:9090"
RESULTS_DIR = Path(__file__).parent.parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

WARMUP_SEC = 60
MEASURE_SEC = 180
TABLES = 10
TABLE_SIZE = 100_000

# Credenciais (iguais às do docker-compose.yml)
MYSQL = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "benchpass",
    "db": "sbtest",
}
POSTGRES = {
    "host": "127.0.0.1",
    "port": 5432,
    "user": "sbuser",
    "password": "benchpass",
    "db": "sbtest",
}

# Queries PromQL para coletar métricas agregadas da janela de medição
# Usamos avg_over_time/rate para pegar a média na janela
PROM_QUERIES = {
    "cpu_percent_avg": 'avg(rate(node_cpu_seconds_total{{mode!="idle"}}[{window}])) * 100',
    "mem_used_bytes_avg": 'avg_over_time(node_memory_MemTotal_bytes[{window}]) - avg_over_time(node_memory_MemAvailable_bytes[{window}])',
    "disk_read_bytes_rate": 'sum(rate(node_disk_read_bytes_total[{window}]))',
    "disk_write_bytes_rate": 'sum(rate(node_disk_written_bytes_total[{window}]))',
    "disk_reads_ops_rate": 'sum(rate(node_disk_reads_completed_total[{window}]))',
    "disk_writes_ops_rate": 'sum(rate(node_disk_writes_completed_total[{window}]))',
}


# -------------------- Helpers --------------------
def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def run_cmd(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Executa comando e retorna o CompletedProcess."""
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def sysbench_base_args(dbms: str, workload: str) -> list[str]:
    """Args comuns para prepare/run do sysbench."""
    if dbms == "mysql":
        return [
            "sysbench",
            workload,
            f"--mysql-host={MYSQL['host']}",
            f"--mysql-port={MYSQL['port']}",
            f"--mysql-user={MYSQL['user']}",
            f"--mysql-password={MYSQL['password']}",
            f"--mysql-db={MYSQL['db']}",
            "--db-driver=mysql",
            f"--tables={TABLES}",
            f"--table-size={TABLE_SIZE}",
        ]
    elif dbms == "postgres":
        return [
            "sysbench",
            workload,
            f"--pgsql-host={POSTGRES['host']}",
            f"--pgsql-port={POSTGRES['port']}",
            f"--pgsql-user={POSTGRES['user']}",
            f"--pgsql-password={POSTGRES['password']}",
            f"--pgsql-db={POSTGRES['db']}",
            "--db-driver=pgsql",
            f"--tables={TABLES}",
            f"--table-size={TABLE_SIZE}",
        ]
    else:
        raise ValueError(f"dbms inválido: {dbms}")


def prepare_dataset(dbms: str, workload: str) -> None:
    """Popula o dataset. Faz cleanup antes para garantir estado limpo."""
    log(f"Limpando dataset anterior (se existir) {dbms}/{workload}...")
    cleanup_args = sysbench_base_args(dbms, workload) + ["cleanup"]
    run_cmd(cleanup_args, check=False)  # ignora erro se não houver nada para limpar

    log(f"Preparando dataset {dbms}/{workload}...")
    args = sysbench_base_args(dbms, workload) + ["prepare"]
    res = run_cmd(args, check=False)
    if res.returncode != 0:
        log(f"Erro no prepare:\nSTDOUT: {res.stdout[:500]}\nSTDERR: {res.stderr[:500]}")
        raise RuntimeError("Falha no prepare")
    log("Dataset preparado.")


def cleanup_dataset(dbms: str, workload: str) -> None:
    """Limpa tabelas criadas pelo sysbench."""
    log(f"Limpando dataset {dbms}/{workload}...")
    args = sysbench_base_args(dbms, workload) + ["cleanup"]
    run_cmd(args, check=False)


def parse_sysbench_output(output: str) -> dict:
    """Extrai métricas da saída do sysbench."""
    metrics = {}
    patterns = {
        "tps": r"transactions:\s+\d+\s+\(([\d.]+)\s+per sec",
        "queries_per_sec": r"queries:\s+\d+\s+\(([\d.]+)\s+per sec",
        "latency_min_ms": r"min:\s+([\d.]+)",
        "latency_avg_ms": r"avg:\s+([\d.]+)",
        "latency_max_ms": r"max:\s+([\d.]+)",
        "latency_p95_ms": r"95th percentile:\s+([\d.]+)",
        "latency_sum_ms": r"sum:\s+([\d.]+)",
        "errors_per_sec": r"errors/s:\s+([\d.]+)",
        "reconnects_per_sec": r"reconnects/s:\s+([\d.]+)",
        "total_events": r"total number of events:\s+(\d+)",
        "total_time_sec": r"total time:\s+([\d.]+)s",
    }
    for key, pattern in patterns.items():
        m = re.search(pattern, output)
        if m:
            metrics[key] = float(m.group(1))
        else:
            metrics[key] = None
    return metrics


def query_prometheus(promql: str, start_ts: float, end_ts: float) -> float | None:
    """Faz query_range no Prometheus e retorna a média dos pontos."""
    try:
        resp = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query_range",
            params={
                "query": promql,
                "start": start_ts,
                "end": end_ts,
                "step": "5s",
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data["status"] != "success":
            return None
        result = data["data"]["result"]
        if not result:
            return None
        # Pega o primeiro resultado e calcula a média dos valores
        values = result[0]["values"]
        nums = [float(v[1]) for v in values if v[1] != "NaN"]
        if not nums:
            return None
        return sum(nums) / len(nums)
    except Exception as e:
        log(f"Erro Prometheus ({promql[:40]}...): {e}")
        return None


def collect_prometheus_metrics(start_ts: float, end_ts: float) -> dict:
    """Coleta todas as métricas do Prometheus para a janela."""
    window_sec = int(end_ts - start_ts)
    window = f"{window_sec}s"
    metrics = {}
    for name, query_template in PROM_QUERIES.items():
        query = query_template.format(window=window)
        metrics[name] = query_prometheus(query, start_ts, end_ts)
    return metrics


def run_sysbench_measure(dbms: str, workload: str, threads: int) -> tuple[dict, float, float]:
    """
    Roda warmup (descartado) + medição com sysbench.
    Implementação manual do warmup para compatibilidade com sysbench < 1.0.20.
    """
    base = sysbench_base_args(dbms, workload) + [
        f"--threads={threads}",
        "--report-interval=5",
        "--rand-type=uniform",
        "--db-ps-mode=disable",
        "--histogram=on",
    ]

    # -------- WARMUP --------
    log(f"Warmup: {dbms}/{workload}, {threads} threads, {WARMUP_SEC}s (descartado)...")
    warmup_args = base + [f"--time={WARMUP_SEC}", "run"]
    res = run_cmd(warmup_args, check=False)
    if res.returncode != 0:
        log(f"Erro no warmup:\n{res.stderr[:500]}")
        raise RuntimeError("Falha no warmup")

    # -------- MEDIÇÃO --------
    log(f"Medição: {dbms}/{workload}, {threads} threads, {MEASURE_SEC}s...")
    measure_start = time.time()
    measure_args = base + [f"--time={MEASURE_SEC}", "run"]
    res = run_cmd(measure_args, check=False)
    if res.returncode != 0:
        log(f"Erro na medição:\n{res.stderr[:500]}")
        raise RuntimeError("Falha na medição")
    measure_end = time.time()

    metrics = parse_sysbench_output(res.stdout)
    return metrics, measure_start, measure_end


def save_result(row: dict, csv_path: Path) -> None:
    """Append do resultado no CSV. Cria header se arquivo novo."""
    write_header = not csv_path.exists()
    with open(csv_path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(row.keys()))
        if write_header:
            writer.writeheader()
        writer.writerow(row)


# -------------------- Main --------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dbms", choices=["mysql", "postgres"], required=True)
    parser.add_argument(
        "--workload",
        choices=["oltp_read_only", "oltp_write_only", "oltp_read_write"],
        required=True,
    )
    parser.add_argument("--threads", type=int, required=True)
    parser.add_argument("--replica", type=int, required=True)
    parser.add_argument(
        "--skip-prepare", action="store_true",
        help="Pular prepare (usar dataset existente)"
    )
    parser.add_argument(
        "--skip-cleanup", action="store_true",
        help="Pular cleanup final (deixar dataset para próxima execução)"
    )
    parser.add_argument(
        "--csv", default="results.csv",
        help="Nome do CSV de saída (em ../results/)"
    )
    args = parser.parse_args()

    csv_path = RESULTS_DIR / args.csv

    # 1. Prepare
    if not args.skip_prepare:
        prepare_dataset(args.dbms, args.workload)
        time.sleep(5)  # dá um respiro antes de medir

    # 2. Run (warmup + medição)
    sb_metrics, measure_start, measure_end = run_sysbench_measure(
        args.dbms, args.workload, args.threads
    )

    # 3. Coleta do Prometheus
    log("Coletando métricas do Prometheus...")
    prom_metrics = collect_prometheus_metrics(measure_start, measure_end)

    # 4. Cleanup
    if not args.skip_cleanup:
        cleanup_dataset(args.dbms, args.workload)

    # 5. Monta row e salva
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "dbms": args.dbms,
        "workload": args.workload,
        "threads": args.threads,
        "replica": args.replica,
        "tables": TABLES,
        "table_size": TABLE_SIZE,
        "warmup_sec": WARMUP_SEC,
        "measure_sec": MEASURE_SEC,
        **sb_metrics,
        **prom_metrics,
    }
    save_result(row, csv_path)

    log(f"✓ OK: TPS={sb_metrics.get('tps')}, p95={sb_metrics.get('latency_p95_ms')}ms, "
        f"CPU%={prom_metrics.get('cpu_percent_avg')}")
    log(f"Resultado salvo em {csv_path}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("Interrompido pelo usuário.")
        sys.exit(130)
    except Exception as e:
        log(f"ERRO: {e}")
        sys.exit(1)
