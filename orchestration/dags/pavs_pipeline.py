"""Airflow DAG: the batch side of Permission-Aware Vector Search, end to end.

    check_services -> ingest -> index -> quality_gate -> leak_tests -> mutation_check -> benchmark -> report

Each task runs one of the project's existing jobs INSIDE the pavs-app container (the image
that already has Spark, the Iceberg jars, pymilvus and FAISS). Airflow only decides order,
retries, timeouts and what happens on failure; it does not need its own copy of Spark.
It talks to Docker through the mounted socket (/var/run/docker.sock).

Why each rule:
  - quality_gate stops the run if the lake and the index disagree, so a half-loaded index
    is never tested, benchmarked or served.
  - leak_tests and mutation_check have retries=0: a security test that fails once and passes
    on a retry is a flaky security test, and must be looked at by a person, not retried to green.
  - mutation_check breaks the permission filter on purpose (test-only switch) and PASSES only
    if the leak tests then FAIL. It proves, on every run, that the tests can still catch a leak.
  - max_active_runs=1: two loads at once would overwrite each other's Milvus collections.
  - schedule=None: new data arrives as a file drop from the Kaggle notebook, so runs are
    triggered (by hand or by the trigger script). A nightly schedule is one line to add.

Params (Trigger DAG w/ config):
  prefix      which files in data/kaggle/ to load: demo100k (default) or corpus1m
  skip_load   true = keep the current index, only run the checks, tests and benchmark
  queries     queries per benchmark point (200 is quick; the report used 500)
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta

import docker
from airflow.sdk import Param, TriggerRule, chain, dag, get_current_context, task
from airflow.sdk.exceptions import AirflowFailException, AirflowSkipException

log = logging.getLogger(__name__)
APP_CONTAINER = os.environ.get("PAVS_APP_CONTAINER", "pavs-app")


def run_in_app(cmd: list[str], env: dict | None = None) -> int:
    """Run a command in the app container, stream its output into the Airflow task log,
    and return the exit code."""
    client = docker.DockerClient(base_url="unix://var/run/docker.sock")
    try:
        container = client.containers.get(APP_CONTAINER)
    except docker.errors.NotFound:
        raise AirflowFailException(f"container {APP_CONTAINER} not found: start the stack first")
    if container.status != "running":
        raise AirflowFailException(f"container {APP_CONTAINER} is {container.status}, not running")

    api = client.api
    ex = api.exec_create(container.id, cmd, workdir="/app",
                         environment={"PYTHONUNBUFFERED": "1", **(env or {})})
    log.info("exec in %s: %s", APP_CONTAINER, " ".join(cmd))
    buf = ""
    for chunk in api.exec_start(ex["Id"], stream=True):
        buf += chunk.decode("utf-8", errors="replace")
        *lines, buf = buf.split("\n")
        for line in lines:
            log.info("%s", line)
    if buf:
        log.info("%s", buf)
    code = api.exec_inspect(ex["Id"])["ExitCode"]
    log.info("exit code %s", code)
    return code


def must_pass(cmd: list[str], env: dict | None = None):
    code = run_in_app(cmd, env)
    if code != 0:
        raise RuntimeError(f"command failed with exit code {code}: {' '.join(cmd)}")


def params() -> dict:
    return get_current_context()["params"]


@dag(
    dag_id="pavs_pipeline",
    description="Load arXiv files -> Iceberg -> Milvus, check quality, prove no leaks, benchmark",
    schedule=None,
    start_date=datetime(2026, 11, 1),
    catchup=False,
    max_active_runs=1,
    tags=["pavs", "bdsrae"],
    default_args={"retries": 1, "retry_delay": timedelta(minutes=1), "owner": "pavs-team"},
    params={
        "prefix": Param("demo100k", type="string", enum=["demo100k", "corpus1m"],
                        description="Which embedding files to load (corpus1m needs about 10 GB free in Docker)"),
        "skip_load": Param(False, type="boolean",
                           description="Keep the current index; only run quality, tests and benchmark"),
        "queries": Param(200, type="integer", minimum=50, maximum=1000,
                         description="Queries per benchmark point"),
    },
    doc_md=__doc__,
)
def pavs_pipeline():

    @task(retries=2, execution_timeout=timedelta(minutes=10))
    def check_services():
        """Milvus, MinIO, Kafka and Postgres must all answer before anything starts."""
        must_pass(["python", "-m", "src.smoke.wait_for"])

    @task(execution_timeout=timedelta(minutes=45))
    def ingest():
        """Spark: data/kaggle/<prefix> files -> Iceberg tables (replaces the tables, so a retry is safe)."""
        p = params()
        if p["skip_load"]:
            raise AirflowSkipException("skip_load=true: keeping the current lakehouse")
        must_pass(["python", "-m", "src.pavs.jobs.ingest", "--prefix", p["prefix"], "--replace"])

    @task(execution_timeout=timedelta(minutes=60))
    def index():
        """Spark joins Iceberg tables once, then the rows are streamed into both Milvus collections."""
        if params()["skip_load"]:
            raise AirflowSkipException("skip_load=true: keeping the current Milvus index")
        must_pass(["python", "-m", "src.pavs.jobs.index"])

    @task(trigger_rule=TriggerRule.NONE_FAILED, retries=0, execution_timeout=timedelta(minutes=20))
    def quality_gate():
        """Counts, nulls, label vocabulary and shares, vectors, and lake == index label by label."""
        must_pass(["python", "-m", "src.pavs.jobs.quality", "--prefix", params()["prefix"]])

    @task(retries=0, execution_timeout=timedelta(minutes=30))
    def leak_tests():
        """The 38-test leakage suite against the live index. Must be all green."""
        must_pass(["python", "-m", "pytest", "tests/test_leakage.py", "-q", "-p", "no:cacheprovider",
                   "--junitxml=results/airflow/leak_tests_junit.xml"])

    @task(retries=0, execution_timeout=timedelta(minutes=30))
    def mutation_check():
        """Disable the filter on purpose; the suite must now FAIL, or it is not testing anything."""
        code = run_in_app(["python", "-m", "pytest", "tests/test_leakage.py", "-q", "-p", "no:cacheprovider",
                           "--junitxml=results/airflow/mutation_check_junit.xml"],
                          env={"PAVS_MUTATION": "no_filter"})
        if code == 0:
            raise AirflowFailException("leak tests PASSED with the filter disabled: the suite cannot catch leaks")
        if code != 1:   # pytest: 1 = some tests failed; 2-5 = crashed / no tests, which proves nothing
            raise AirflowFailException(f"pytest did not run cleanly (exit code {code}), so the check proves nothing")
        log.info("as expected, leak tests failed with the filter disabled (exit code %s)", code)

    @task(retries=0, execution_timeout=timedelta(minutes=60))
    def benchmark():
        """Recall and latency of every method at every permission level."""
        p = params()
        must_pass(["python", "-m", "src.pavs.bench", "--prefix", p["prefix"], "--queries", str(p["queries"]),
                   "--tag", f"airflow_{p['prefix']}"])

    @task(retries=0, execution_timeout=timedelta(minutes=5))
    def report():
        """One Markdown page per run: results/airflow/pipeline_report_<prefix>.md"""
        ctx = get_current_context()
        p = ctx["params"]
        must_pass(["python", "-m", "src.pavs.jobs.pipeline_report", "--prefix", p["prefix"],
                   "--tag", f"airflow_{p['prefix']}", "--run-id", ctx["run_id"]])

    chain(check_services(), ingest(), index(), quality_gate(), leak_tests(), mutation_check(), benchmark(), report())


pavs_pipeline()
