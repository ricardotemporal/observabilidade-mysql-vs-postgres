# Relatório de Análise Estatística — Observabilidade MySQL vs PostgreSQL

- **Total de execuções:** 36
- **Combinações únicas:** 12
- **Réplicas por combinação:** 3
- **Taxa de erros observada:** 0.0000 erros/s (média)

## Tabela 1 — Estatística descritiva por combinação

Cada linha = 3 réplicas. TPS e p95 com média e intervalo de confiança 95%.

| DBMS | Workload | Threads | TPS média [IC95%] | p95 (ms) [IC95%] | CV TPS (%) |
|---|---|---:|---|---|---:|
| postgres | oltp_read_only | 50 | 1107.02 [1095.51, 1118.53] | 88.63 [86.33, 90.92] | 0.42 |
| postgres | oltp_read_only | 10 | 1043.44 [1039.39, 1047.49] | 32.53 [32.53, 32.53] | 0.16 |
| mysql | oltp_write_only | 50 | 1888.09 [1805.61, 1970.57] | 56.19 [51.00, 61.37] | 1.76 |
| mysql | oltp_write_only | 10 | 697.47 [671.81, 723.14] | 22.29 [21.29, 23.28] | 1.48 |
| mysql | oltp_read_write | 10 | 488.83 [371.36, 606.30] | 32.04 [24.28, 39.80] | 9.67 |
| mysql | oltp_read_write | 50 | 640.29 [606.80, 673.78] | 136.10 [104.37, 167.83] | 2.11 |
| postgres | oltp_write_only | 10 | 2373.19 [2177.01, 2569.38] | 5.00 [4.43, 5.58] | 3.33 |
| postgres | oltp_write_only | 50 | 3388.06 [3340.58, 3435.54] | 63.70 [62.05, 65.35] | 0.56 |
| mysql | oltp_read_only | 10 | 936.52 [931.59, 941.45] | 36.24 [36.24, 36.24] | 0.21 |
| mysql | oltp_read_only | 50 | 991.55 [986.94, 996.16] | 90.78 [90.78, 90.78] | 0.19 |
| postgres | oltp_read_write | 50 | 752.82 [644.40, 861.25] | 97.56 [93.19, 101.94] | 5.80 |
| postgres | oltp_read_write | 10 | 715.08 [685.42, 744.75] | 34.97 [31.84, 38.10] | 1.67 |

## Tabela 2 — Uso de recursos por combinação (médias)

| DBMS | Workload | Threads | CPU (%) | Escrita disco (MB/s) | Leitura disco (MB/s) |
|---|---|---:|---:|---:|---:|
| postgres | oltp_read_only | 50 | 4.42 | 0.77 | 0.0718 |
| postgres | oltp_read_only | 10 | 5.60 | 0.37 | 0.0006 |
| mysql | oltp_write_only | 50 | 5.27 | 56.54 | 0.0210 |
| mysql | oltp_write_only | 10 | 4.47 | 51.84 | 0.0018 |
| mysql | oltp_read_write | 10 | 5.82 | 41.81 | 0.0162 |
| mysql | oltp_read_write | 50 | 5.04 | 37.02 | 0.0002 |
| postgres | oltp_write_only | 10 | 5.51 | 16.21 | 0.0005 |
| postgres | oltp_write_only | 50 | 5.14 | 13.40 | 0.0001 |
| mysql | oltp_read_only | 10 | 5.60 | 2.38 | 0.0104 |
| mysql | oltp_read_only | 50 | 4.76 | 0.05 | 0.0002 |
| postgres | oltp_read_write | 50 | 4.57 | 4.62 | 0.0004 |
| postgres | oltp_read_write | 10 | 5.63 | 5.92 | 0.0030 |

## H1 — Há diferença significativa de TPS entre MySQL e PostgreSQL?

- **H₀:** μ(TPS_MySQL) = μ(TPS_Postgres)
- **H₁:** μ(TPS_MySQL) ≠ μ(TPS_Postgres)
- **α = 0,05**

Pares comparados: 18 combinações (workload × threads × réplica).

**Teste de normalidade das diferenças (Shapiro-Wilk):** W = 0.6860, p = 0.0001 → diferenças NÃO normais.

**Teste aplicado:** Wilcoxon pareado
- Estatística: 0.0000
- p-valor: 0.000008

**Médias globais de TPS:**
- MySQL: 940.46
- PostgreSQL: 1563.27
- Diferença: +66.22% (PostgreSQL em relação a MySQL)

**Conclusão:** p = 0.0000 < 0,05 → **rejeitamos H₀**. Há diferença estatisticamente significativa de TPS entre os dois SGBDs.

## H2 — O efeito do SGBD sobre TPS depende do perfil de carga?

- **H₀:** não há interação entre DBMS e workload
- **H₁:** há interação (efeito do DBMS varia entre workloads)
- **α = 0,05**

**ANOVA (tipo II):**

| Fator | Soma Sq | df | F | p-valor |
|---|---:|---:|---:|---:|
| C(dbms) | 3491036.89 | 1 | 46.7861 | 0.000000 |
| C(workload) | 13368285.36 | 2 | 89.5794 | 0.000000 |
| C(threads) | 1579148.28 | 1 | 21.1634 | 0.000077 |
| C(dbms):C(workload) | 4195907.28 | 2 | 28.1163 | 0.000000 |
| Residual | 2163891.93 | 29 | - | - |

**Conclusão:** p(interação) = 0.0000 < 0,05 → **rejeitamos H₀**. A diferença de desempenho entre MySQL e PostgreSQL varia significativamente conforme o perfil de carga.

## H3 — A vazão escala linearmente com a concorrência (10 → 50 threads)?

Escalabilidade linear ideal: 5× threads ⇒ 5× TPS.
Calculamos o **fator de escalabilidade** observado = TPS(50) / TPS(10).
Fator ideal = 5,00. Valores abaixo indicam saturação.

| DBMS | Workload | TPS@10 | TPS@50 | Fator observado | Eficiência (% do ideal) |
|---|---|---:|---:|---:|---:|
| postgres | oltp_read_only | 1043.44 | 1107.02 | 1.06 | 21.2% |
| mysql | oltp_write_only | 697.47 | 1888.09 | 2.71 | 54.1% |
| mysql | oltp_read_write | 488.83 | 640.29 | 1.31 | 26.2% |
| postgres | oltp_write_only | 2373.19 | 3388.06 | 1.43 | 28.6% |
| mysql | oltp_read_only | 936.52 | 991.55 | 1.06 | 21.2% |
| postgres | oltp_read_write | 715.08 | 752.82 | 1.05 | 21.1% |

**Interpretação:** fatores << 5 indicam saturação (CPU, locks, I/O ou fila). Em cenários OLTP em dataset pequeno cabendo em memória, a saturação tipicamente ocorre por contenção de locks ou por CPU.
