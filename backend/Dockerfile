# Same immutable Python/Linux base for dependency build and runtime.
ARG PYTHON_IMAGE=python:3.14.6-slim-bookworm@sha256:4c92ffcde4dd6f1ff72a24518f49fd4990b27134987dfa31a733badde66df9f8
FROM ${PYTHON_IMAGE} AS base
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 \
    PATH=/opt/venv/bin:$PATH
# Freeze OS package inputs too; signature verification remains enabled.
COPY backend/container/debian.sources /etc/apt/sources.list.d/debian.sources
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 libstdc++6 \
    && rm -rf /var/lib/apt/lists/*

FROM base AS dependencies
WORKDIR /workspace/backend
RUN python -m venv /opt/venv && python -m pip install --only-binary=:all: pip==26.1.2
COPY backend/constraints.txt backend/requirements.txt backend/requirements-dev.txt backend/requirements-cpu.txt ./
# Isolate the CPU index; never let a generic Linux torch wheel pull in CUDA.
RUN python -m pip install --only-binary=:all: --no-deps -r requirements-cpu.txt \
    && python -m pip install --only-binary=:all: -r requirements-dev.txt \
    && python -m pip check
COPY backend/scripts/ ./scripts/
RUN python -m scripts.verify_dependencies

FROM dependencies AS tested
COPY backend/app/ ./app/
COPY backend/tests/ ./tests/
COPY backend/model-artifacts.json backend/Dockerfile backend/cloudbuild.yaml ./
COPY backend/container/ ./container/
COPY .dockerignore .gcloudignore /workspace/
COPY backend/db/ ./db/
RUN python -m unittest discover -s tests \
    && python -c "from pathlib import Path; Path('/tmp/tests-passed').touch()"

FROM dependencies AS worker-models
COPY backend/app/config.py backend/app/model_artifacts.py ./app/
COPY backend/model-artifacts.json ./
RUN python -m scripts.download_models --role worker --output /models

FROM dependencies AS api-models
COPY backend/app/config.py backend/app/model_artifacts.py ./app/
COPY backend/model-artifacts.json ./
RUN python -m scripts.download_models --role api --output /models

FROM base AS runtime
WORKDIR /app
COPY --from=tested /opt/venv /opt/venv
COPY --from=tested /tmp/tests-passed /opt/tests-passed
COPY backend/app/ ./app/
COPY backend/scripts/ ./scripts/
COPY backend/model-artifacts.json ./
ENV APP_ENV=production CONTAINER_MODEL_ROOT=/opt/models \
    EMBEDDING_MODEL_PATH=/opt/models/embedding \
    HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 \
    HF_HOME=/tmp/huggingface HOME=/tmp TOKENIZERS_PARALLELISM=false \
    OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
ARG SOURCE_REVISION=unrecorded
LABEL org.opencontainers.image.revision=${SOURCE_REVISION}
USER 65532:65532

FROM runtime AS worker
COPY --from=worker-models /models /opt/models
ENTRYPOINT ["python", "-m", "app.worker"]
# Safe default: print CLI usage rather than unexpectedly polling/claiming work.
CMD ["--help"]

FROM runtime AS api
COPY --from=api-models /models /opt/models
ENV RERANKING_MODEL_PATH=/opt/models/reranking PORT=8080
EXPOSE 8080
ENTRYPOINT ["python", "-m", "scripts.start_api"]
