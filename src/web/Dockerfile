# Leptos Development Dockerfile
FROM rust:latest AS development


RUN wget https://github.com/cargo-bins/cargo-binstall/releases/latest/download/cargo-binstall-x86_64-unknown-linux-musl.tgz
RUN tar -xvf cargo-binstall-x86_64-unknown-linux-musl.tgz
RUN cp cargo-binstall /usr/local/cargo/bin

RUN apt-get update -y \
  && apt-get install -y --no-install-recommends clang pkg-config libssl-dev curl

# Install Node.js (required for pnpm)
RUN curl -fsSL https://deb.nodesource.com/setup_lts.x | bash - \
  && apt-get install -y nodejs

ENV CI=true
# Install pnpm
RUN npm install -g pnpm

# Install cargo-leptos with cargo cache
RUN --mount=type=cache,target=/usr/local/cargo/registry \
    --mount=type=cache,target=/usr/local/cargo/git \
    cargo binstall cargo-leptos -y && cargo install -f wasm-bindgen-cli --version 0.2.105

# Add the WASM target
RUN rustup target add wasm32-unknown-unknown

# Set working directory
WORKDIR /app

# Copy workspace root and structure
# Note: build context is project root (.)
COPY . .

# Set working directory to web package
WORKDIR /app/src/web

# Pre-build dependencies with caching for faster subsequent builds
RUN --mount=type=cache,target=/usr/local/cargo/registry \
    --mount=type=cache,target=/usr/local/cargo/git \
    --mount=type=cache,target=/app/target \
    cargo build --release --bin yappr-web

EXPOSE 3000
ENV PORT=3000
ENV SERVICE_NAME="yappr-web"
# Default command for development
ENTRYPOINT ["cargo", "leptos", "watch"]