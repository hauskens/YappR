FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS base
WORKDIR /src
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

RUN apt update && apt install -y ffmpeg
RUN apt-get clean && rm -rf /var/lib/apt/lists/*

RUN --mount=type=cache,target=/root/.cache/uv \
  --mount=type=bind,source=uv.lock,target=uv.lock \
  --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
  uv sync --frozen --no-install-project --no-dev

ADD . .
RUN --mount=type=cache,target=/root/.cache/uv \
  uv sync --frozen --no-dev

ENV PATH="/src/.venv/bin:$PATH"


FROM base AS worker
ENTRYPOINT ["celery"]
CMD ["--app","main.celery","--workdir","app","worker","--loglevel=info","--concurrency=1"]

FROM base AS app
EXPOSE 5000
ENTRYPOINT ["/src/entrypoint.sh"]
# CMD [ "app/main.py" ]
