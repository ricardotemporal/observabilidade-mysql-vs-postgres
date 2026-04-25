# Scripts de execução e análise

## Pré-requisitos

```bash
cd ~/projetos/observabilidade-db/scripts
pip3 install --user --break-system-packages -r requirements.txt
```

## Fluxo completo

### 1. Piloto (uma execução)
```bash
python3 run_single.py --dbms mysql --workload oltp_read_write --threads 10 --replica 1 --csv piloto.csv
```

### 2. Experimento completo (36 execuções)
```bash
python3 run_all.py
```
Saída: `../results/results.csv` com 36 linhas.

### 3. Análise estatística
```bash
python3 analyze.py
```
Saída: `../docs/analise.md` com todas as tabelas e testes de hipótese.

### 4. Gráficos
```bash
python3 plots.py
```
Saída: 5 arquivos `.png` em `../docs/figures/`.

## Retomar execução após falha

```bash
python3 run_all.py --start-from N
```

## Reexecutar análise com outro CSV

```bash
python3 analyze.py --input outro.csv --output outro.md
python3 plots.py --input outro.csv --outdir outras_figs
```
