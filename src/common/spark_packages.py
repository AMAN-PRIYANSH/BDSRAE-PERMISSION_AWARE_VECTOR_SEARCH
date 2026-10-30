"""Spark session factory for the project.

One place that knows every jar version and the Iceberg catalog settings.
  - Iceberg tables live in MinIO (bucket "lakehouse"), written with S3FileIO
  - The Iceberg catalog (table names -> metadata files) lives in Postgres (JDBC catalog)

Running this file with --warm-cache downloads the jars (used in the Dockerfile).
"""
import os
import sys

SPARK_VERSION = "4.0.4"
ICEBERG_VERSION = "1.11.0"

PACKAGES = [
    f"org.apache.iceberg:iceberg-spark-runtime-4.0_2.13:{ICEBERG_VERSION}",
    f"org.apache.iceberg:iceberg-aws-bundle:{ICEBERG_VERSION}",
    f"org.apache.spark:spark-sql-kafka-0-10_2.13:{SPARK_VERSION}",
    "org.postgresql:postgresql:42.7.4",
]


def get_spark(app_name="pavs", master="local[2]", driver_memory="2g", extra=None):
    from pyspark.sql import SparkSession

    s3 = os.environ.get("PAVS_S3_ENDPOINT", "http://minio:9000")
    b = (
        SparkSession.builder.appName(app_name)
        .master(master)
        .config("spark.driver.memory", driver_memory)
        .config("spark.jars.packages", ",".join(PACKAGES))
        .config("spark.jars.ivy", os.environ.get("SPARK_JARS_IVY", "/opt/ivy"))
        .config("spark.sql.extensions",
                "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions")
        .config("spark.sql.catalog.lake", "org.apache.iceberg.spark.SparkCatalog")
        .config("spark.sql.catalog.lake.catalog-impl", "org.apache.iceberg.jdbc.JdbcCatalog")
        .config("spark.sql.catalog.lake.uri", "jdbc:postgresql://postgres:5432/iceberg")
        .config("spark.sql.catalog.lake.jdbc.user", "iceberg")
        .config("spark.sql.catalog.lake.jdbc.password", "iceberg")
        .config("spark.sql.catalog.lake.jdbc.schema-version", "V1")
        .config("spark.sql.catalog.lake.warehouse", "s3://lakehouse/warehouse")
        .config("spark.sql.catalog.lake.io-impl", "org.apache.iceberg.aws.s3.S3FileIO")
        .config("spark.sql.catalog.lake.s3.endpoint", s3)
        .config("spark.sql.catalog.lake.s3.path-style-access", "true")
        .config("spark.sql.catalog.lake.s3.access-key-id", os.environ.get("AWS_ACCESS_KEY_ID", "minioadmin"))
        .config("spark.sql.catalog.lake.s3.secret-access-key", os.environ.get("AWS_SECRET_ACCESS_KEY", "minioadmin"))
        .config("spark.sql.catalog.lake.client.region", os.environ.get("AWS_REGION", "us-east-1"))
        # AWS SDK >= 2.30 sends new checksums that our (older) MinIO rejects on batch delete
        # ("Missing required header: Content-Md5"). Iceberg's switch for older S3-compatible stores:
        .config("spark.sql.catalog.lake.client.legacy-md5-plugin-enabled", "true")
        .config("spark.sql.defaultCatalog", "lake")
        .config("spark.ui.enabled", "false")
    )
    for k, v in (extra or {}).items():
        b = b.config(k, v)
    spark = b.getOrCreate()
    spark.sparkContext.setLogLevel("WARN")
    return spark


def ensure_bucket(name="lakehouse"):
    """Create the MinIO bucket for Iceberg if it does not exist yet."""
    import boto3

    s3 = boto3.client("s3", endpoint_url=os.environ.get("PAVS_S3_ENDPOINT", "http://minio:9000"))
    existing = [b["Name"] for b in s3.list_buckets().get("Buckets", [])]
    if name not in existing:
        s3.create_bucket(Bucket=name)
    return name


if __name__ == "__main__" and "--warm-cache" in sys.argv:
    # Only resolve and download jars; no catalog connection is made.
    from pyspark.sql import SparkSession

    s = (SparkSession.builder.master("local[1]")
         .config("spark.jars.packages", ",".join(PACKAGES))
         .config("spark.jars.ivy", os.environ.get("SPARK_JARS_IVY", "/opt/ivy"))
         .getOrCreate())
    print("Spark", s.version, "- jars cached")
    s.stop()
