# App image: Python 3.12 + Java 17 + PySpark 4.0.4 + project libraries.
# Everything (Spark jobs, benchmarks, API, tests) runs in this one image.
FROM python:3.12-slim-bookworm

RUN apt-get update \
 && apt-get install -y --no-install-recommends openjdk-17-jre-headless procps curl \
 && rm -rf /var/lib/apt/lists/*

ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    SPARK_JARS_IVY=/opt/ivy \
    HF_HOME=/models

WORKDIR /app

# CPU-only PyTorch: avoids ~2.5 GB of NVIDIA CUDA libraries this laptop cannot use.
RUN pip install --index-url https://download.pytorch.org/whl/cpu "torch>=2.6,<3"

# Lock the CPU torch build as a constraint, so installing the other libraries
# can never replace it with the CUDA build from PyPI.
COPY requirements.txt .
RUN pip freeze | grep -i '^torch==' > /tmp/torch-constraint.txt \
 && cat /tmp/torch-constraint.txt \
 && pip install -r requirements.txt -c /tmp/torch-constraint.txt \
 && python -c "import torch; assert not torch.cuda.is_available(); print('torch', torch.__version__, 'CPU build OK')" \
 && ! pip list 2>/dev/null | grep -qi '^nvidia-'

# Download the Spark jars (Iceberg, AWS bundle, Kafka connector, Postgres driver)
# once at build time, so they are baked into the image.
COPY src/common/spark_packages.py /tmp/spark_packages.py
RUN python /tmp/spark_packages.py --warm-cache

CMD ["sleep", "infinity"]
