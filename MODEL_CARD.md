# Model card: embedding model used by Permission-Aware Vector Search

We did **not train** a model. We use a public pre-trained sentence-embedding model to turn text into
vectors, and the project's contribution is the system around it (permission filtering, lakehouse,
streaming permission changes, leakage testing). This card documents how the model is used and what that
means for safety.

## Model details

| Item | Value |
|---|---|
| Name | `sentence-transformers/all-MiniLM-L6-v2` |
| Type | Sentence-embedding transformer (6 layers, MiniLM), mean pooling |
| Output | 384-dimensional vector, L2-normalised (so inner product = cosine similarity) |
| Size | about 22.7 M parameters, about 90 MB |
| Licence | Apache-2.0 |
| Input limit | 256 word pieces; longer text is cut off (most arXiv abstracts fit; very long ones are truncated) |
| Where it ran | Kaggle notebook, Tesla T4 GPU, fp16 storage (`notebooks/01_kaggle_embed_arxiv.ipynb`) |
| Library | sentence-transformers 6.2.0 |

Why this model (and not a bigger one): it is free, small enough to embed 1,000,000 abstracts in about
19 minutes on a free T4, 384 dimensions keep the Milvus index for 1M documents small enough for a 16 GB
laptop (1M x 384 x 4 bytes = 1.5 GB per copy), and it is widely used as a baseline, so results are
comparable to other work. The permission-filtering results do not depend on which embedding model is used.

## Intended use in this project

* Encode the **title + abstract** of each arXiv paper (corpus) and the **title** of 2,000 held-out papers
  (queries), for nearest-neighbour search.
* Search only; no text is generated.

## Out-of-scope uses

* Not a classifier and not a source of truth for access rights: **access labels never come from the
  model**. They come from the policy (`src/pavs/policy.py`) and are stored as metadata in Iceberg and
  Milvus. A model must not decide who may see a document.
* Not evaluated for non-English text, code, or private company documents.

## Data

See [DATA_CARD.md](DATA_CARD.md). Public arXiv metadata (CC0), author names dropped, access labels
synthetic. No personal data.

## Evaluation (as used here)

The model itself is not re-evaluated. What we measure is the retrieval system that uses it:
Recall@10 against exact search over the documents each user is allowed to see, latency, leakage
(must be zero) and revocation delay. See `TECHNICAL_REPORT.md` and `notebooks/02_results.ipynb`.

## Risks and Responsible-AI notes

| Risk | What it means here | What we do |
|---|---|---|
| Embeddings leak content | Research shows text can be partly reconstructed from embeddings ("embedding inversion"). A vector of a restricted document is sensitive data. | Vectors of restricted documents are never returned to unauthorised users: the filter runs inside Milvus before results are formed, and the API returns only id, title, label and score, never vectors. |
| Similarity is not permission | A highly similar restricted document must still be hidden. | Permission filter is applied inside the search (not after), tested for every role with a leakage test suite (38 tests, 0 leaks). |
| Bias in what is "similar" | The model was trained mostly on English web text; some fields or writing styles may be ranked lower. | Out of scope for this project; noted as a limitation. Recall is measured per selectivity level, not per field. |
| Truncation | Text beyond 256 word pieces is ignored. | Accepted; abstracts are short. |

## Versions

Pinned in `requirements.txt` and explained in `VERSIONS.md`.
