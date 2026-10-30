"""Mutation check for the leakage suite (test code only; production code has no switch for this).

PAVS_MUTATION=no_filter  replaces the permission filter builder with one that allows everything.
The leakage tests MUST then fail; if they still passed, they would not be testing anything.
Run:  PAVS_MUTATION=no_filter python -m pytest tests/test_leakage.py -q      (failures expected)
"""
import os

import pytest


@pytest.fixture(scope="session", autouse=True)
def _mutation():
    mode = os.environ.get("PAVS_MUTATION", "")
    if mode != "no_filter":
        yield
        return
    from src.pavs import policy
    original = policy.milvus_filter
    policy.milvus_filter = lambda labels: ""          # BROKEN ON PURPOSE: no permission filter
    print("\n*** MUTATION ACTIVE: permission filter disabled, leakage tests are expected to FAIL ***")
    yield
    policy.milvus_filter = original
