"""Create the two Milvus collections and load documents into them.

docs_filter : one collection, HNSW on the vector + INVERTED index on access_label.
              Permission = filter expression "access_label in [...]".
docs_part   : the same documents, physically split into one partition per access label.
              Permission = list of partitions to search.

Both are loaded from the same rows, so benchmark differences come only from the method.
"""
import time

import numpy as np
from pymilvus import DataType, MilvusClient

from src.pavs import policy
from src.pavs.search import COLL_FILTER, COLL_PART

DIM = 384
HNSW = {"M": 16, "efConstruction": 200}


def _schema():
    s = MilvusClient.create_schema(auto_id=False)
    s.add_field("doc_id", DataType.INT64, is_primary=True)
    s.add_field("arxiv_id", DataType.VARCHAR, max_length=32)
    s.add_field("title", DataType.VARCHAR, max_length=2048)
    s.add_field("access_label", DataType.VARCHAR, max_length=32)
    s.add_field("dept", DataType.VARCHAR, max_length=16)
    s.add_field("vec", DataType.FLOAT_VECTOR, dim=DIM)
    return s


def create_collections(client: MilvusClient, lite: bool = False, drop: bool = True):
    for name in (COLL_FILTER, COLL_PART):
        if drop and client.has_collection(name):
            client.drop_collection(name)

    idx = client.prepare_index_params()
    if lite:
        idx.add_index(field_name="vec", index_type="FLAT", metric_type="COSINE")
    else:
        idx.add_index(field_name="vec", index_type="HNSW", metric_type="COSINE", params=HNSW)
        idx.add_index(field_name="access_label", index_type="INVERTED")
    client.create_collection(COLL_FILTER, schema=_schema(), index_params=idx, consistency_level="Bounded")

    if not lite:                                   # Milvus Lite has no partitions
        idx2 = client.prepare_index_params()
        idx2.add_index(field_name="vec", index_type="HNSW", metric_type="COSINE", params=HNSW)
        client.create_collection(COLL_PART, schema=_schema(), index_params=idx2, consistency_level="Bounded")
        for label in policy.LABELS:
            client.create_partition(COLL_PART, partition_name=policy.partition_name(label))


def insert_batch(client: MilvusClient, doc_ids, arxiv_ids, titles, labels, depts, vecs, lite=False):
    """Insert one batch into both collections. vecs: float32 array (n, 384), L2-normalised."""
    vecs = np.asarray(vecs, dtype=np.float32)
    rows = [{"doc_id": int(d), "arxiv_id": a, "title": (t or "")[:500], "access_label": l,
             "dept": dp, "vec": v.tolist()}
            for d, a, t, l, dp, v in zip(doc_ids, arxiv_ids, titles, labels, depts, vecs)]
    client.insert(COLL_FILTER, rows)
    if not lite:
        by_label = {}
        for r in rows:
            by_label.setdefault(r["access_label"], []).append(r)
        for label, part_rows in by_label.items():
            client.insert(COLL_PART, part_rows, partition_name=policy.partition_name(label))
    return len(rows)


def apply_relabels(client: MilvusClient, changes, lite=False):
    """Apply access-label changes {doc_id: new_label} to both collections.

    docs_filter: upsert the row with the new label (same primary key).
    docs_part:   the row must MOVE partition, so delete it and insert it into the new label's partition.
    Returns the number of documents changed.
    """
    changes = {int(d): l for d, l in changes.items() if l in policy.LABELS}
    if not changes:
        return 0
    ids = list(changes)
    rows = client.query(COLL_FILTER, filter=f"doc_id in {ids}",
                        output_fields=["doc_id", "arxiv_id", "title", "access_label", "dept", "vec"],
                        consistency_level="Strong")
    new_rows = []
    for r in rows:
        r = dict(r)
        r["access_label"] = changes[int(r["doc_id"])]
        r["vec"] = [float(x) for x in r["vec"]]
        new_rows.append(r)
    if not new_rows:
        return 0
    client.upsert(COLL_FILTER, new_rows)
    if not lite:
        client.delete(COLL_PART, ids=[r["doc_id"] for r in new_rows])
        by_label = {}
        for r in new_rows:
            by_label.setdefault(r["access_label"], []).append(r)
        for label, part_rows in by_label.items():
            client.insert(COLL_PART, part_rows, partition_name=policy.partition_name(label))
    return len(new_rows)


def finish(client: MilvusClient, lite=False):
    """Flush, build indexes and load into memory. Returns seconds taken."""
    t = time.time()
    names = [COLL_FILTER] + ([] if lite else [COLL_PART])
    for n in names:
        client.flush(n)
    for n in names:
        client.load_collection(n)
    return time.time() - t
