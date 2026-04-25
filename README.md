# Observabilidade em Bancos de Dados Relacionais: MySQL vs PostgreSQL

Estudo comparativo de desempenho e observabilidade entre MySQL 8.4 e PostgreSQL 17, realizado como trabalho da disciplina **Model Avaliação de Desempenho** (Universidade de Fortaleza, 7º semestre de Ciência da Computação).

## Autores

- Álvaro Araújo (2510552)
- Camila Martins (2310286)
- Ricardo Temporal (2310292)

## Resumo

Aplicamos um projeto de experimentos fatorial completo (2 SGBDs × 3 perfis de carga × 2 níveis de concorrência × 3 réplicas = **36 execuções**) usando sysbench como gerador de carga e Prometheus + Grafana como stack de observabilidade. Os resultados foram analisados com testes estatísticos formais (Wilcoxon pareado, ANOVA fatorial) e três hipóteses foram confirmadas com significância estatística (p < 0,05).

## Principais achados

- **PostgreSQL é 66% mais rápido em média**, com vantagem máxima em escrita pura (+123% em oltp_write_only).
- **PostgreSQL escreve 76% menos em disco** mesmo fazendo mais transações, evidenciando a eficiência do WAL com group commit.
- **Saturação precoce** em cargas de leitura: aumentar concorrência de 10 para 50 threads gerou apenas 6% de ganho em TPS.
- Os dois SGBDs oferecem observabilidade nativa rica e comparável, com diferenças nas pontas (PostgreSQL: auto_explain; MySQL: histograma nativo de latência).

## Stack utilizada

- **SGBDs:** MySQL 8.4 LTS, PostgreSQL 17
- **Benchmark:** sysbench 1.0.20 (módulos oltp_read_only, oltp_write_only, oltp_read_write)
- **Observabilidade:** Prometheus, Grafana, mysqld_exporter, postgres_exporter, node_exporter
- **Orquestração:** Docker Compose
- **Análise:** Python (pandas, scipy, statsmodels, matplotlib)
- **Ambiente:** Windows 11 + WSL2 (Ubuntu 24.04), AMD Ryzen 5 5600, 32 GB RAM, SSD NVMe

## Estrutura do repositório

- docker-compose.yml — Stack completa (7 serviços)
- config/mysql/my.cnf — Tuning MySQL com observabilidade plena
- config/postgres/postgresql.conf — Tuning PostgreSQL com pg_stat_statements + auto_explain
- prometheus/prometheus.yml
- grafana/provisioning/
- scripts/run_single.py — Executa uma combinação do experimento
- scripts/run_all.py — Orquestra as 36 execuções (aleatorizadas)
- scripts/analyze.py — Estatística + testes de hipótese
- scripts/plots.py — Geração dos gráficos
- scripts/requirements.txt
- results/results.csv — Dataset bruto das 36 execuções
- docs/analise.md — Relatório estatístico
- docs/figures/ — 5 gráficos em PNG
- docs/trabalho_avaliacao_desempenho.docx

## Como reproduzir

### Pré-requisitos

- Docker Desktop com integração WSL2 (Windows) ou Docker Engine (Linux)
- Python 3.11+
- sysbench 1.0.20+

### Subir o ambiente

    docker compose up -d
    docker compose ps

### Instalar dependências Python

    cd scripts
    pip3 install --user --break-system-packages -r requirements.txt

### Rodar o experimento

    python3 run_all.py

Tempo estimado: ~3 horas (36 execuções × ~5 minutos cada).

### Analisar os resultados

    python3 analyze.py
    python3 plots.py

## Endpoints durante a execução

| Serviço | URL | Credenciais |
|---|---|---|
| Grafana | http://localhost:3000 | admin / admin |
| Prometheus | http://localhost:9090 | — |
| MySQL | localhost:3306 | root / benchpass |
| PostgreSQL | localhost:5432 | sbuser / benchpass |

## Licença

Trabalho acadêmico. Código sob MIT License.
