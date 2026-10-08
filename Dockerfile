# syntax=docker/dockerfile:1
FROM node:22-bookworm-slim AS web-build
WORKDIR /build/web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-fund
COPY web/ ./
RUN npm run build

FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    OCI_CONTROL_DATA_DIR=/data \
    OCI_CONTROL_WEB_DIR=/app/web/dist \
    OCI_CONTROL_HOST=0.0.0.0 \
    OCI_CONTROL_PORT=8787 \
    OCI_CONFIG_FILE=/oci/config
RUN groupadd --gid 10001 ocicontrol \
    && useradd --uid 10001 --gid ocicontrol --create-home ocicontrol \
    && mkdir -p /data /oci \
    && chown ocicontrol:ocicontrol /data
WORKDIR /app
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt
COPY server/ ./server/
COPY --from=web-build /build/web/dist ./web/dist
COPY --chmod=755 scripts/container-entrypoint.sh /usr/local/bin/oci-control-entrypoint
RUN chmod -R a+rX /app
USER 10001:10001
EXPOSE 8787
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8787/api/health', timeout=3).close()"
ENTRYPOINT ["oci-control-entrypoint"]
CMD ["python", "-m", "server"]
