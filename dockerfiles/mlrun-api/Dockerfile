# Copyright 2023 Iguazio
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

ARG MLRUN_PYTHON_VERSION=3.11
ARG MLRUN_UV_IMAGE=ghcr.io/astral-sh/uv:latest

FROM proteantecs/mlrun-mysqldump:1.9.2 AS builder


FROM ${MLRUN_UV_IMAGE} AS uv-image

FROM cgr.dev/chainguard/wolfi-base AS base

ARG UID=1000

# need to be redeclared since used in the from
ARG MLRUN_PYTHON_VERSION=3.11

# Add Python and other required system packages
RUN apk add --no-cache \
    python-${MLRUN_PYTHON_VERSION} \
    py${MLRUN_PYTHON_VERSION}-pip \
    py${MLRUN_PYTHON_VERSION}-setuptools \
    py${MLRUN_PYTHON_VERSION}-wheel \
    gcc \
    git \
    procps \
    sqlite \
    vim \
    mariadb-client \
    curl \
    ca-certificates \
    tini \
    shadow \
    libffi-dev \
    openssl-dev \
    linux-headers \
    bash

# Create mlrun user and group
RUN useradd -u $UID mlrun

COPY --from=builder /usr/local/mysql/bin/mysqldump /usr/local/bin/
RUN chmod +x /usr/local/bin/mysqldump

LABEL maintainer="yaronh@iguazio.com"
LABEL org="iguazio.com"

ENV UV_SYSTEM_PYTHON=true \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

WORKDIR /mlrun

RUN --mount=from=uv-image,source=/uv,target=/bin/uv \
    --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=dockerfiles/mlrun-api/locked-requirements.txt,target=locked-requirements.txt \
    uv pip sync --require-hashes locked-requirements.txt --python-version ${MLRUN_PYTHON_VERSION}

COPY ./pipeline-adapters ./pipeline-adapters

COPY ./dockerfiles/mlrun-api/start_api.sh ./dockerfiles/mlrun-api/start_api.sh

RUN --mount=from=uv-image,source=/uv,target=/bin/uv \
    uv pip install ./pipeline-adapters/mlrun-pipelines-kfp-common --python-version ${MLRUN_PYTHON_VERSION} && \
    uv pip install ./pipeline-adapters/mlrun-pipelines-kfp-v1-8 --python-version ${MLRUN_PYTHON_VERSION}

COPY . .
RUN chmod -R a+rX /mlrun/server/py/schemas/proto

RUN --mount=from=uv-image,source=/uv,target=/bin/uv \
    --mount=type=cache,target=/root/.cache/uv \
    uv pip install .[complete-api,kfp18] --python-version ${MLRUN_PYTHON_VERSION}

# Cleanup
RUN rm -rf ./server/go \
    && python${MLRUN_PYTHON_VERSION} -m pip uninstall pip -y \
    && rm -rf /usr/lib/python${MLRUN_PYTHON_VERSION}/ensurepip || true

RUN rm /usr/share/python-wheels/pip*.whl
RUN rm -rf /var/cache/apk/* && rm -rf /lib/apk/db/*

RUN chmod +x ./dockerfiles/mlrun-api/start_api.sh

VOLUME /mlrun/db
ENV PYTHONPATH=/mlrun/server/py
ENV MLRUN_HTTPDB__DSN='sqlite:////mlrun/db/mlrun.db?check_same_thread=false'
ENV MLRUN_HTTPDB__LOGS_PATH=/mlrun/db/logs
ENV MLRUN_HTTPDB__DIRPATH=/mlrun/db
ENV MLRUN_HTTPDB__PORT=8080
ENV MLRUN_HTTPDB__HTTP_CONNECTION_TIMEOUT_KEEP_ALIVE=11
ENV MLRUN_IS_API_SERVER=true
ENV MLRUN_IGNORE_ENV_FILE=true

# Uvicorn settings
ENV UVICORN_PORT=${MLRUN_HTTPDB__PORT}
ENV UVICORN_TIMEOUT_KEEP_ALIVE=${MLRUN_HTTPDB__HTTP_CONNECTION_TIMEOUT_KEEP_ALIVE}
ENV MLRUN_SERVICES__SERVICE_NAME=api

ENTRYPOINT ["tini", "--"]
CMD ["bash", "./dockerfiles/mlrun-api/start_api.sh"]
