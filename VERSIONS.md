# Locked versions and why

Checked on 29 Oct 2026. Every tool is free and open source.

| Component | Version | Licence | Why this version |
|---|---|---|---|
| Milvus (vector database) | 3.0.3 | Apache 2.0 | Version the official Milvus install docs use. 3.0.4 came out 26 Oct 2026 with no release notes yet, so we wait. |
| pymilvus (Python client) | 3.0.2 | Apache 2.0 | Client line matching Milvus server 3.0.x |
| etcd (Milvus metadata) | 3.5.25 | Apache 2.0 | Pinned in the official Milvus 3.0.3 compose file |
| MinIO (object storage) | milvusdb/minio RELEASE.2024-12-18 | AGPLv3 | MinIO stopped publishing free Docker images in Oct 2025. Milvus publishes its own mirrored copy, so we use that. Old build with a known CVE: fine for an isolated local test bed, not for production. |
| Apache Spark / PySpark | 4.0.4 | Apache 2.0 | Iceberg 1.11 supports Spark 3.5, 4.0 and 4.1, not 4.2. A plain "pip install pyspark" gives 4.2 and breaks. 4.0.4 is the newest version that also has a matching Kafka connector jar. |
| Apache Iceberg | 1.11.0 | Apache 2.0 | Supports Spark 4.0 (status: maintained). 1.12.0 is newer but not yet checked against our stack. |
| Iceberg catalog | JDBC catalog on Postgres 17 | PostgreSQL | Safe when a streaming job and a batch job write at the same time (a plain file catalog on object storage is not) |
| Apache Kafka | 4.3.2 (apache/kafka image, KRaft, no ZooKeeper) | Apache 2.0 | Official image. Bitnami Kafka images are no longer published. 4.4.0 is one week old, so we use the previous stable line. |
| Java | 17 | GPL+CE | Supported by Spark 4.0 |
| Python | 3.12 | PSF | Newest numpy needs 3.12+; PySpark 4.0 supports it |
| pandas / numpy / pyarrow | <3 / <2.4 / <21 | BSD / BSD / Apache 2.0 | Kept inside the range PySpark 4.0 was released with |
| PyTorch | CPU build from download.pytorch.org | BSD | No NVIDIA GPU on the laptop; the CPU build avoids ~2.5 GB of unused CUDA libraries |
| sentence-transformers + all-MiniLM-L6-v2 | 6.2.0 | Apache 2.0 | Small (384 numbers per text), free, runs locally, no data leaves the machine |
| FAISS (faiss-cpu) | 1.15.1 | MIT | Exact ground truth and library baseline |
| FastAPI / Streamlit | latest | MIT / Apache 2.0 | Search API and demo UI |
| Apache Airflow | 3.3.2 (apache/airflow:3.3.2-python3.12) | Apache 2.0 | Added 4 Nov 2026. Airflow 2 is end of life (April 2026), so we start on the 3.x line. 3.3.2 is the newest patch release (17 Sep 2026). Its metadata goes in a separate `airflow` database in the project Postgres. |
| Docker Desktop | user's install | Free for personal and education use | Runs the whole stack |
| Dataset: arXiv metadata | Kaggle Cornell-University/arxiv | CC0 (public domain) | No personal data, openly licensed, ~2.3M records |

## Traps found during verification

1. pymilvus reads an environment variable named MILVUS_URI on import and crashes if it is not an http address. Our code uses PAVS_MILVUS_URI instead.
2. HNSW recall measured on random vectors is very low (0.28 at efSearch 64) but perfect on clustered, embedding-like vectors. All benchmarks must use real arXiv embeddings, never random data.
3. Newer PyTorch wheels on PyPI pull NVIDIA CUDA packages on Linux. The Dockerfile installs the CPU build first and locks it with a pip constraint.
4. Bind-mounting Windows folders into Linux containers is slow for etcd and breaks the ownership change Milvus needs. All databases use named Docker volumes.
5. Airflow 3 runs several processes (scheduler, API server, DAG processor). They must share one JWT secret, or tasks fail to report back; the compose file sets it explicitly (local-only value).
