# Pipeline run report: demo100k

Airflow run `manual__2026-11-04T16:02:49.687952+00:00`, written 2026-11-04 16:07:23.

## 1. Data-quality gate

**PASSED** on 100,000 documents.

| Check | Result | Detail |
|---|---|---|
| counts | pass | source 100,000 | documents 100,000 | doc_embeddings 100,000 |
| no_nulls | pass | 0 rows with a missing id, department or label |
| label_vocabulary | pass | 11 labels, all known to the policy |
| label_shares | pass | largest deviation z=2.40 (limit 5.0) |
| embeddings | pass | 0 vectors missing, wrong length or NaN |
| label_rule | pass | 0 of 2016 sampled labels differ from policy.py |
| milvus_row_count | pass | lake 100,000 | docs_filter 100,000 | docs_part 100,000 |
| milvus_per_label | pass | all 11 labels match in both collections |

## 2. Leakage tests

38 of 38 passed, 0 failed (21 s).

## 3. Benchmark

Recall@10 by share of the corpus the user may see:

| visible share | faiss_post_10x | faiss_postfilter | faiss_prefilter | milvus_filter | milvus_partition |
|---|---|---|---|---|---|
| 1 | 0.976 | 0.962 | 0.962 | 0.981 | 0.988 |
| 0.5 | 0.970 | 0.483 | 0.951 | 0.969 | 0.979 |
| 0.2 | 0.645 | 0.201 | 0.755 | 0.983 | 0.979 |
| 0.05 | 0.448 | 0.041 | 0.698 | 1.000 | 0.999 |
| 0.01 | 0.106 | 0.007 | 0.484 | 1.000 | 1.000 |
| 0.001 | 0.007 | 0.001 | 0.079 | 1.000 | 1.000 |

p95 latency (ms):

| visible share | faiss_post_10x | faiss_postfilter | faiss_prefilter | milvus_filter | milvus_partition |
|---|---|---|---|---|---|
| 1 | 0.7 | 0.4 | 0.7 | 5.0 | 5.3 |
| 0.5 | 0.6 | 0.3 | 0.4 | 6.2 | 3.9 |
| 0.2 | 0.5 | 0.4 | 0.4 | 5.3 | 3.7 |
| 0.05 | 0.5 | 0.5 | 0.4 | 5.1 | 4.1 |
| 0.01 | 0.6 | 0.4 | 0.4 | 6.4 | 6.2 |
| 0.001 | 0.7 | 0.6 | 0.4 | 6.0 | 5.2 |

