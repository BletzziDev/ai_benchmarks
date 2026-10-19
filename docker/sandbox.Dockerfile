# syntax=docker/dockerfile:1
# Sandbox image for `--sandbox docker`. Build with scripts/build_sandbox_image.sh (handles proxies/custom CAs).
# Pinned versions keep evaluations reproducible; bump the tag when changing them.
FROM python:3.12-slim

# An optional build secret "ca" (a PEM bundle) is trusted only during the build; it is not stored in the image.
RUN --mount=type=secret,id=ca,target=/run/secrets/ca,required=false \
    if [ -s /run/secrets/ca ]; then export PIP_CERT=/run/secrets/ca; \
       printf 'Acquire::https::CaInfo "/run/secrets/ca";\n' > /etc/apt/apt.conf.d/99ca; fi; \
    apt-get update && apt-get install -y --no-install-recommends git procps \
 && rm -rf /var/lib/apt/lists/* \
 && pip install --no-cache-dir pytest==9.1.1 hypothesis==6.170.1 \
 && rm -f /etc/apt/apt.conf.d/99ca

# Unprivileged user matching the harness default (uid/gid 65534 = nobody)
RUN mkdir -p /workspace /home/sandbox && chown 65534:65534 /workspace /home/sandbox
USER 65534:65534
WORKDIR /workspace
ENV HOME=/home/sandbox PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0
CMD ["sleep", "infinity"]
