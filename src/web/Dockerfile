# Leptos Development Dockerfile
FROM rust:latest as development


RUN wget https://github.com/cargo-bins/cargo-binstall/releases/latest/download/cargo-binstall-x86_64-unknown-linux-musl.tgz
RUN tar -xvf cargo-binstall-x86_64-unknown-linux-musl.tgz
RUN cp cargo-binstall /usr/local/cargo/bin

RUN apt-get update -y \
  && apt-get install -y --no-install-recommends clang pkg-config libssl-dev curl

# Install cargo-leptos
RUN cargo binstall cargo-leptos -y

# Add the WASM target
RUN rustup target add wasm32-unknown-unknown

# Set working directory
WORKDIR /app

# Copy workspace root and structure  
# Note: build context is project root (.)
COPY . .

# Set working directory to web package
WORKDIR /app/src/web

RUN cargo build

EXPOSE 3000

# Default command for development
ENTRYPOINT ["cargo", "leptos", "watch"]