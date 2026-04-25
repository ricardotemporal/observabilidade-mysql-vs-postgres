#!/usr/bin/env python3
"""
run_all.py — Orquestra as 36 execuções do experimento fatorial.

Projeto fatorial:
  - SGBD: mysql, postgres (2 níveis)
  - Workload: oltp_read_only, oltp_write_only, oltp_read_write (3 níveis)
  - Threads: 10, 50 (2 níveis)
  - Réplicas: 3

Total: 2 × 3 × 2 × 3 = 36 execuções.

Estratégia:
- Aleatorização em blocos: dentro de cada (dbms, workload) rodamos as 2×3=6
  execuções (threads × réplicas) em ordem aleatória, preparando o dataset 1x.
- Ordem dos blocos (dbms, workload) também aleatorizada.
- Isso reduz re-preparação do dataset sem perder aleatorização.

Uso:
    python3 run_all.py                    # roda tudo
    python3 run_all.py --dry-run          # só mostra o plano
    python3 run_all.py --seed 42          # reproduz exatamente a mesma ordem
"""

import argparse
import random
import subprocess
import sys
import time
from datetime import datetime
from itertools import product
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
RUN_SINGLE = SCRIPT_DIR / "run_single.py"

DBMS_LIST = ["mysql", "postgres"]
WORKLOADS = ["oltp_read_only", "oltp_write_only", "oltp_read_write"]
THREAD_LEVELS = [10, 50]
REPLICAS = [1, 2, 3]


def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def build_plan(seed: int) -> list[dict]:
    """
    Monta plano de execução em blocos aleatorizados.

    Um 'bloco' é uma combinação (dbms, workload). Dentro dele rodamos 6 execuções
    (2 threads × 3 réplicas). O dataset é preparado uma vez no início do bloco
    e limpo ao final.
    """
    rng = random.Random(seed)

    # Lista de blocos (dbms, workload)
    blocks = list(product(DBMS_LIST, WORKLOADS))
    rng.shuffle(blocks)

    plan = []
    for block_idx, (dbms, workload) in enumerate(blocks):
        # Dentro do bloco: aleatoriza threads × réplicas
        inner = list(product(THREAD_LEVELS, REPLICAS))
        rng.shuffle(inner)

        for i, (threads, replica) in enumerate(inner):
            plan.append({
                "dbms": dbms,
                "workload": workload,
                "threads": threads,
                "replica": replica,
                "is_first_in_block": (i == 0),
                "is_last_in_block": (i == len(inner) - 1),
            })
    return plan


def print_plan(plan: list[dict]) -> None:
    print(f"\n{'#':>3}  {'DBMS':<10} {'Workload':<18} {'Threads':>7} {'Replica':>7}")
    print("-" * 55)
    for i, step in enumerate(plan, 1):
        marker = ""
        if step["is_first_in_block"]:
            marker += " [prepare]"
        if step["is_last_in_block"]:
            marker += " [cleanup]"
        print(f"{i:>3}  {step['dbms']:<10} {step['workload']:<18} "
              f"{step['threads']:>7} {step['replica']:>7}{marker}")


def run_step(step: dict, csv_name: str) -> bool:
    """Invoca run_single.py com os flags apropriados. Retorna True se OK."""
    cmd = [
        "python3", str(RUN_SINGLE),
        "--dbms", step["dbms"],
        "--workload", step["workload"],
        "--threads", str(step["threads"]),
        "--replica", str(step["replica"]),
        "--csv", csv_name,
    ]
    if not step["is_first_in_block"]:
        cmd.append("--skip-prepare")
    if not step["is_last_in_block"]:
        cmd.append("--skip-cleanup")

    res = subprocess.run(cmd)
    return res.returncode == 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42,
                        help="Seed do aleatorizador (default 42)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Só imprime o plano, não executa")
    parser.add_argument("--csv", default="results.csv",
                        help="Nome do CSV de saída")
    parser.add_argument("--start-from", type=int, default=1,
                        help="Retomar a partir do passo N (1-indexed)")
    args = parser.parse_args()

    plan = build_plan(args.seed)
    total = len(plan)
    log(f"Plano gerado: {total} execuções (seed={args.seed}).")
    print_plan(plan)

    if args.dry_run:
        log("Dry-run: plano impresso, não executando.")
        return

    est_minutes = total * 5  # ~5 min por execução (prepare 30s + warmup 60s + run 180s + cleanup)
    log(f"Estimativa de tempo total: ~{est_minutes} min ({est_minutes/60:.1f}h).")
    log("Iniciando em 5 segundos... (Ctrl+C para abortar)")
    time.sleep(5)

    failures = []
    start_time = time.time()
    for i, step in enumerate(plan, 1):
        if i < args.start_from:
            continue
        log(f"\n{'='*60}")
        log(f"[{i}/{total}] {step['dbms']} | {step['workload']} | "
            f"threads={step['threads']} | replica={step['replica']}")
        log(f"{'='*60}")

        step_start = time.time()
        ok = run_step(step, args.csv)
        elapsed = time.time() - step_start

        if not ok:
            log(f"✗ FALHA no passo {i}. Continuando com os próximos.")
            failures.append(i)
        else:
            log(f"✓ Passo {i} concluído em {elapsed:.1f}s.")

    total_elapsed = time.time() - start_time
    log(f"\n{'='*60}")
    log(f"Concluído: {total - len(failures)}/{total} com sucesso.")
    log(f"Tempo total: {total_elapsed/60:.1f} min.")
    if failures:
        log(f"Falhas nos passos: {failures}")
        log("Use --start-from N para retomar do passo N.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("\nInterrompido pelo usuário.")
        sys.exit(130)
