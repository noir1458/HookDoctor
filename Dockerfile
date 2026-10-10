FROM ubuntu:24.04
ARG TARGETARCH
RUN test "$TARGETARCH" = amd64 \
    && apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
       build-essential binutils python3 ca-certificates \
    && rm -rf /var/lib/apt/lists/*
ENV LC_ALL=C.UTF-8 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/workspace/src
WORKDIR /workspace
CMD ["bash"]
