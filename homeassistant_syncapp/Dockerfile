ARG BUILD_FROM=ghcr.io/home-assistant/base:3.23
FROM ${BUILD_FROM}

ARG BUILD_VERSION
ARG BUILD_ARCH

RUN apk add --no-cache \
    ca-certificates \
    git \
    py3-yaml \
    python3 \
    && test -x /usr/bin/git \
    && test -x /usr/bin/python3 \
    && test "$(/usr/bin/git --exec-path)" = "/usr/libexec/git-core" \
    && test -x /usr/libexec/git-core/git-remote-https \
    && test -r /etc/ssl/certs/ca-certificates.crt \
    && test -d /etc/ssl/certs

COPY app /app
COPY run.sh /run.sh
RUN chmod a+x /run.sh

LABEL \
    io.hass.version="${BUILD_VERSION}" \
    io.hass.type="app" \
    io.hass.arch="${BUILD_ARCH}" \
    org.opencontainers.image.title="HomeAssistant SyncApp" \
    org.opencontainers.image.source="https://github.com/Togarriapa/HomeAssistant_SyncApp"

CMD ["/run.sh"]
