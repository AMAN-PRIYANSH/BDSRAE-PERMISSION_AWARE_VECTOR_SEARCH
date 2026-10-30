# Data Card: arXiv corpus with synthetic access labels

## 1. Summary

| Item | Value |
|---|---|
| Source | arXiv metadata snapshot, Kaggle dataset `Cornell-University/arxiv` |
| Licence | CC0 1.0 (public domain dedication) |
| Snapshot used | Kaggle version available on 29 Oct 2026 |
| Records in source file | 3,224,635 lines |
| Duplicate arXiv ids found | 93 (latest record kept for each id) |
| Unique papers | 3,224,542 |
| Search corpus | 1,000,000 papers, uniform random sample, seed 42 |
| Demo slice | first 100,000 rows of the corpus (also a uniform random sample) |
| Test queries | 2,000 different papers (never in the corpus); query text = title |
| Fields kept | arXiv id, title, abstract, categories, update date |
| Fields dropped | authors, submitter, comments, journal reference, DOI, report number, licence, versions |
| Embedding model | sentence-transformers/all-MiniLM-L6-v2 (384 numbers, L2-normalised, stored as float16) |
| Document text embedded | title + ". " + abstract (truncated by the model at 256 tokens) |

## 2. Why this dataset

- The course rules allow only public, synthetic or openly licensed data with no real personal data.
- arXiv metadata is CC0, so it can be copied, processed and redistributed.
- It is large enough for big-data scale tests (millions of real documents).
- Its subject categories give a natural way to assign documents to departments.

The project brief also suggested the Enron e-mail corpus. We did not use it: it contains private e-mails of real
people, which conflicts with the course rule against real personal data.

## 3. Personal data

- Author and submitter names exist in the source file. **We drop them before any processing**, so no
  person's name is stored in the lakehouse, the vector index or the results.
- Titles and abstracts are scientific text written for publication. They are not personal data about the reader
  or the user of the search system.

## 4. Synthetic access labels

The access-control labels are **invented for the experiment**. They do not reflect any real organisation.

Each paper gets exactly one label, decided by a fixed rule:

1. Department = from the paper's first (primary) arXiv category:
   `cs.*` -> cs, `math.*` -> math, physics families (astro-ph, cond-mat, hep-*, nucl-*, physics.*, quant-ph,
   math-ph, nlin, gr-qc) -> physics, everything else -> other.
2. Bucket = CRC32 checksum of the arXiv id, modulo 10,000 (deterministic, reproducible, same in Spark and Python).
3. Label from the bucket:

| Bucket | Label | Share of corpus |
|---|---|---|
| 0-9 | board-restricted | 0.1% |
| 10-99 | hr-restricted | 0.9% |
| 100-999 | `<department>`-confidential | 9% |
| 1,000-4,999 | `<department>`-internal | 40% |
| 5,000-9,999 | public | 50% |

Because the bucket comes from a checksum, labels are spread evenly and are independent of the paper's topic within a
department. This is a deliberate simplification: in a real company, sensitive documents would cluster by topic.
See Limitations.

Measured distribution in the 1,000,000-document corpus (from the ingest job, `logs/20_load_1m.txt`):

| Label | Documents | Share |
|---|---:|---:|
| public | 499,920 | 49.99% |
| physics-internal | 191,818 | 19.18% |
| cs-internal | 104,498 | 10.45% |
| math-internal | 75,981 | 7.60% |
| physics-confidential | 43,476 | 4.35% |
| other-internal | 27,685 | 2.77% |
| cs-confidential | 23,353 | 2.34% |
| math-confidential | 17,215 | 1.72% |
| hr-restricted | 8,977 | 0.90% |
| other-confidential | 6,100 | 0.61% |
| board-restricted | 977 | 0.10% |

## 5. Known issues and limitations

- **Duplicates:** 93 duplicate ids in the source; handled by keeping the latest record.
- **Category imbalance:** by primary category, physics is about 48% of the sample, cs about 26%, math about 19%
  and other about 7% (from the internal-label shares above). Department-level selectivity therefore differs
  between departments.
- **Labels are random within a department:** real restricted documents are often about specific topics (e.g. HR,
  finance). Our labels do not capture this, which may make filtered search look easier or harder than in practice.
- **Single language:** almost all abstracts are English. Results do not say anything about other languages.
- **Truncation:** text longer than 256 tokens is cut by the embedding model; long abstracts lose their tail.

## 6. Intended use

Benchmarking permission-aware vector search (latency, recall and leakage) for a university course project.

Not intended for: ranking real papers, making claims about authors, or any decision about real people.
