FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS base
WORKDIR /src
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV BUN_INSTALL_CACHE_DIR="/bun-cache"
RUN apt update && apt install -y ffmpeg npm curl unzip \
  && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://bun.com/install | bash
ENV BUN_INSTALL="/root/.bun"
ENV PATH="$BUN_INSTALL/bin:/src/.venv/bin:$PATH"
RUN --mount=type=cache,target=/root/.cache/uv \
  --mount=type=bind,source=uv.lock,target=uv.lock \
  --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
  uv sync --frozen --no-install-project --no-dev

FROM base AS main
RUN --mount=type=cache,target=/root/.cache/uv \
  --mount=type=bind,source=uv.lock,target=uv.lock \
  --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
  uv sync --frozen --no-dev
RUN --mount=type=cache,target=/bun-cache \
  --mount=type=bind,source=package.json,target=package.json \
  --mount=type=bind,source=bun.lock,target=bun.lock \
  --mount=type=bind,source=yarn.lock,target=yarn.lock \
  bun install
COPY . .
RUN bun run build


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

RUN --mount=type=cache,target=/root/.cache/uv \
  --mount=type=bind,source=uv.lock,target=uv.lock \
  --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
  uv sync --frozen --no-dev --group worker
COPY app ./app
COPY pyproject.toml uv.lock .

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
RUN --mount=type=cache,target=/root/.cache/uv \
  --mount=type=bind,source=uv.lock,target=uv.lock \
  --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
  uv sync --frozen --no-dev --group bot
ENV NLTK_ENABLED=false
COPY . .
CMD ["python", "-m", "bot.main"]

