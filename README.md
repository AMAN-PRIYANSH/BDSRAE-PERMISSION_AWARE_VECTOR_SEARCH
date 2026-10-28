# Permission-Aware Vector Search

BDSRAE Level 3 project (Big Data Systems and Responsible AI Engineering), PES University.

Team: Akshat Agarwal (PES1UG24AM024), Aman Priyansh (PES1UG24AM030), Aditya Kalloli (PES1UG24AM015)

## Problem

An enterprise search system must never return a document a user is not allowed to see.
We build semantic (vector) search with permission filtering, measure how restrictive
filters change latency and recall, and run leakage tests with users of different roles.

## Stack

All free and open source. Exact versions and the reason for each are in VERSIONS.md.

- Storage: Apache Iceberg tables on MinIO, catalog in Postgres
- Processing: Apache Spark (batch embeddings, streaming permission changes)
- Streaming: Apache Kafka
- Vector search: Milvus (main), FAISS (baseline and exact ground truth)
- Embeddings: sentence-transformers all-MiniLM-L6-v2
- API and demo: FastAPI, Streamlit

## Status

Stage 1 (environment verification) in progress.

## How to run (Windows, Docker Desktop)

1. Double-click `checks\00_check_machine.bat`
2. Double-click `checks\01_build_and_start.bat` (first run downloads about 5-6 GB)
3. Double-click `checks\02_run_smoke_tests.bat`
4. To free memory afterwards: `checks\09_stop_stack.bat`

Results are written to the `logs` folder.
