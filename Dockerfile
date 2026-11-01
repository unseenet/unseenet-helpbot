# unseenet-helpbot in a container: the help bot on the node image (core, chiavdf, Tor,
# tini). Vault, helpbot.toml, the GitHub cache and the state in /data. The model runs
# elsewhere: an Ollama container beside it (compose.yaml) or any OpenAI-style server.
#
#   docker run --rm -v helpbot:/data ghcr.io/unseenet/helpbot            # writes an example helpbot.toml
#   docker run --rm -v helpbot:/data -e UNSEENET_VAULT_PASSPHRASE=... ghcr.io/unseenet/helpbot init
#   docker run -d --name helpbot -v helpbot:/data -e UNSEENET_VAULT_PASSPHRASE=... ghcr.io/unseenet/helpbot
#
# See the README ("In Docker") and compose.yaml.
ARG NODE_IMAGE=ghcr.io/unseenet/node:latest

FROM ${NODE_IMAGE} AS build
USER root
# a core newer than the image's (from git, before a release) builds chiavdf here
RUN apk add --no-cache gcc g++ musl-dev python3-dev libffi-dev cmake make gmp-dev git
ENV BUILD_VDF_CLIENT=N
COPY pyproject.toml README.md LICENSE helpbot.example.toml /src/
COPY src /src/src
RUN /opt/unseenet/bin/pip install --no-cache-dir /src \
 && find /opt/unseenet -name __pycache__ -type d -prune -exec rm -rf {} +

FROM ${NODE_IMAGE}
USER root
COPY --from=build /opt/unseenet /opt/unseenet
COPY helpbot.example.toml /opt/unseenet-helpbot/helpbot.example.toml
COPY docker/entrypoint.sh /usr/local/bin/unseenet-helpbot-entrypoint
RUN chmod 755 /usr/local/bin/unseenet-helpbot-entrypoint
ENV UNSEENET_DATA=/data
VOLUME /data
HEALTHCHECK NONE
LABEL org.opencontainers.image.title="Unseenet help bot" \
      org.opencontainers.image.description="Answers questions in Unseenet's help group from the project's docs, with a local model" \
      org.opencontainers.image.source="https://github.com/unseenet/unseenet-helpbot" \
      org.opencontainers.image.url="https://github.com/unseenet/unseenet-helpbot#in-docker" \
      org.opencontainers.image.licenses="Apache-2.0"
ENTRYPOINT ["/sbin/tini", "--", "unseenet-helpbot-entrypoint"]
CMD []
