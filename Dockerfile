FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS base
WORKDIR /src
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"

RUN apt update && apt install -y ffmpeg npm curl \
  && npm install -g pnpm \
  && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN --mount=type=cache,target=/root/.cache/uv \
  --mount=type=bind,source=uv.lock,target=uv.lock \
  --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
  uv sync --frozen --no-install-project --no-dev
COPY pnpm-lock.yaml package.json .
RUN --mount=type=cache,id=pnpm,target=/pnpm/store pnpm install --frozen-lockfile
ENV PATH="/src/.venv/bin:$PATH"

FROM base AS main
ADD . .
RUN --mount=type=cache,target=/root/.cache/uv \
  uv sync --frozen --no-dev
RUN --mount=type=cache,id=pnpm,target=/pnpm/store pnpm run build



FROM nvidia/cuda:12.9.0-cudnn-runtime-ubuntu24.04 AS worker-gpu
WORKDIR /src
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
ADD https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.0-1_all.deb ./cuda-keyring_1.0-1_all.deb 
RUN apt clean && \
    dpkg -i cuda-keyring_1.0-1_all.deb && \
    apt update && \
    apt install -y ffmpeg python3 libcudnn8-dev libcudnn8\
  && apt-get clean && rm -rf /var/lib/apt/lists/*
RUN --mount=type=cache,target=/root/.cache/uv \
  --mount=type=bind,source=uv.lock,target=uv.lock \
  --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
  uv sync --frozen --no-install-project --no-dev --group worker

ADD . .
RUN --mount=type=cache,target=/root/.cache/uv \
  uv sync --frozen --no-dev --group worker

ENV PATH="/src/.venv/bin:$PATH"
ENV SERVICE_NAME="worker-gpu"
ENTRYPOINT ["celery"]
CMD ["--app","app.main.celery","worker","--loglevel=info","--concurrency=1", "-Q", "gpu-queue"]

FROM main AS worker
ENV SERVICE_NAME="worker"
ENTRYPOINT ["celery"]

FROM main AS app
ENV SERVICE_NAME="app"
EXPOSE 5000
ENTRYPOINT ["/src/entrypoint.sh"]

FROM base AS bot
ENV SERVICE_NAME="bot"
ADD . .
RUN --mount=type=cache,target=/root/.cache/uv \
  uv sync --frozen --no-dev --group bot
ENV NLTK_ENABLED=false
CMD ["python", "-m", "bot.main"]

