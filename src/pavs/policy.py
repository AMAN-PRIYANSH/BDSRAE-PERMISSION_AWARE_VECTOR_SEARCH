"""Access-control policy: labels, roles, users, and how a document gets its label.

Every document gets exactly ONE access label. A role is a SET of labels it may read.
A user has exactly one role. Search may only ever return documents whose label is in
the user's role.

Why one label per document (not a list of roles per document):
  - a document readable by many roles is stored once, not copied per role
  - revoking access to a document = changing one value
  - partitions can be "one per label" without duplicates

Label assignment is synthetic but deterministic: it uses CRC32 of the arXiv id, so
Spark (crc32 SQL function) and Python (zlib.crc32) give the same answer everywhere.
"""
import zlib

# ---------------------------------------------------------------- departments
PHYSICS_PREFIXES = ("astro-ph", "cond-mat", "gr-qc", "hep-", "nucl-", "physics", "quant-ph", "math-ph", "nlin")


def department(categories: str) -> str:
    """Department from the FIRST (primary) arXiv category, e.g. 'cs.LG stat.ML' -> 'cs'."""
    primary = (categories or "").split(" ")[0]
    if primary.startswith("cs."):
        return "cs"
    if primary.startswith("math.") or primary == "math":
        return "math"
    if primary.startswith(PHYSICS_PREFIXES):
        return "physics"
    return "other"


DEPARTMENTS = ["cs", "math", "physics", "other"]

# ---------------------------------------------------------------- labels
# Bucket = crc32(arxiv_id) % 10000. Share of documents per label (independent of department):
#   0-9      board-restricted   0.1%
#   10-99    hr-restricted      0.9%
#   100-999  <dept>-confidential 9%
#   1000-4999 <dept>-internal   40%
#   5000-9999 public            50%
BUCKETS = 10_000


def bucket(arxiv_id: str) -> int:
    return zlib.crc32(arxiv_id.encode("utf-8")) % BUCKETS


def access_label(arxiv_id: str, categories: str) -> str:
    b = bucket(arxiv_id)
    d = department(categories)
    if b < 10:
        return "board-restricted"
    if b < 100:
        return "hr-restricted"
    if b < 1000:
        return f"{d}-confidential"
    if b < 5000:
        return f"{d}-internal"
    return "public"


LABELS = (["public", "hr-restricted", "board-restricted"]
          + [f"{d}-internal" for d in DEPARTMENTS]
          + [f"{d}-confidential" for d in DEPARTMENTS])

# ---------------------------------------------------------------- roles
ROLES = {
    "intern":             ["public"],
    "cs_engineer":        ["public", "cs-internal"],
    "cs_manager":         ["public", "cs-internal", "cs-confidential"],
    "math_researcher":    ["public", "math-internal"],
    "physics_researcher": ["public", "physics-internal"],
    "physics_manager":    ["public", "physics-internal", "physics-confidential"],
    "other_analyst":      ["public", "other-internal"],
    "hr_officer":         ["public", "hr-restricted"],
    "board_member":       ["public", "board-restricted", "hr-restricted"],
    "admin":              list(LABELS),
}

# ---------------------------------------------------------------- users (synthetic)
USERS = {
    "ananya.intern":   "intern",
    "rahul.cs":        "cs_engineer",
    "meera.csmgr":     "cs_manager",
    "kiran.math":      "math_researcher",
    "farah.physics":   "physics_researcher",
    "vikram.phymgr":   "physics_manager",
    "sana.analyst":    "other_analyst",
    "deepa.hr":        "hr_officer",
    "arjun.board":     "board_member",
    "root.admin":      "admin",
}

# Sanity checks run on import: a typo here must fail loudly, not leak quietly.
for _role, _labels in ROLES.items():
    _unknown = set(_labels) - set(LABELS)
    assert not _unknown, f"role {_role} grants unknown labels {_unknown}"
for _user, _role in USERS.items():
    assert _role in ROLES, f"user {_user} has unknown role {_role}"


def allowed_labels(user: str) -> list:
    """Labels a user may read. Unknown user -> empty list (fail closed)."""
    role = USERS.get(user)
    if role is None:
        return []
    return list(ROLES.get(role, []))


def milvus_filter(labels) -> str | None:
    """Milvus boolean expression built ONLY from allowlisted labels. None = deny everything."""
    clean = sorted({l for l in labels if l in LABELS})
    if not clean:
        return None
    return "access_label in [" + ", ".join(f'"{l}"' for l in clean) + "]"


def partition_name(label: str) -> str:
    """Milvus partition names allow letters, digits and underscores only."""
    assert label in LABELS, label
    return "p_" + label.replace("-", "_")
