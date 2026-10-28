"""Smoke test 5: embedding speed on this laptop's CPU.

Encodes 2,000 abstract-length texts with all-MiniLM-L6-v2 and projects how
long 1M and 2.3M documents would take. This decides whether embeddings are
made on the laptop or on a free Kaggle/Colab GPU.

Run:  python -m src.smoke.test_embed
"""
import time

import numpy as np
import torch
from sentence_transformers import SentenceTransformer

MODEL = "sentence-transformers/all-MiniLM-L6-v2"
N = 2000

BASE = ("We propose a scalable method for approximate nearest neighbour search under "
        "attribute constraints and evaluate it on large benchmark collections. ")


def main():
    t = time.time()
    model = SentenceTransformer(MODEL, device="cpu")
    print(f"Model loaded in {time.time() - t:.1f}s | torch {torch.__version__} | "
          f"threads={torch.get_num_threads()} | max_seq_length={model.max_seq_length}")
    # ~150-200 words, like an arXiv abstract
    texts = [f"Paper {i}. " + BASE * 8 for i in range(N)]

    model.encode(texts[:64], batch_size=64)  # warm-up
    t = time.time()
    emb = model.encode(texts, batch_size=64, normalize_embeddings=True, show_progress_bar=False)
    dt = time.time() - t
    rate = N / dt
    assert emb.shape == (N, 384), emb.shape
    assert np.allclose(np.linalg.norm(emb, axis=1), 1.0, atol=1e-3)
    print(f"[PASS] {N} texts -> {emb.shape} float32 in {dt:.1f}s = {rate:.0f} docs/s")
    for total in (100_000, 1_000_000, 2_300_000):
        print(f"       projected for {total:>9,} docs on this CPU: {total / rate / 3600:.2f} h")
    print("EMBED SMOKE TEST: ALL PASSED")


if __name__ == "__main__":
    main()
