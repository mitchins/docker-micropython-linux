FROM debian:bookworm-slim

ARG MICROPYTHON_VERSION=v1.28.0

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      build-essential \
      ca-certificates \
      git \
      libffi8 \
      libffi-dev \
      pkg-config \
      python3 \
    && git clone --depth 1 --branch ${MICROPYTHON_VERSION} https://github.com/micropython/micropython.git \
    && cd micropython \
    && cd ports/unix \
    && make submodules \
    && make \
    && make install \
    && cd / \
    && rm -rf micropython \
    && apt-get purge --auto-remove -y \
      build-essential \
      git \
      pkg-config \
      python3 \
    && rm -rf /var/lib/apt/lists/*

ENTRYPOINT ["/usr/local/bin/micropython"]
