FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
WORKDIR /src
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

RUN --mount=type=cache,target=/root/.cache/uv \
  --mount=type=bind,source=uv.lock,target=uv.lock \
  --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
  uv sync --frozen --no-install-project --no-dev

ADD . .
RUN --mount=type=cache,target=/root/.cache/uv \
  uv sync --frozen --no-dev

ENV PATH="/src/.venv/bin:$PATH"

EXPOSE 5000
ENTRYPOINT [ ]
CMD [ "python", "app/main.py" ]
