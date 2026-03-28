ARG BASE_IMAGE=nvcr.io/nvidia/tritonserver:23.08-py3
FROM ${BASE_IMAGE}

ARG TORCH_INSTALL_FLAVOR=cpu
ARG TORCH_VERSION=2.10.0

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

COPY requirements.txt /tmp/requirements.txt

RUN python3 -m pip install --upgrade pip && \
    if [ "${TORCH_INSTALL_FLAVOR}" = "cpu" ]; then \
        python3 -m pip install --extra-index-url https://download.pytorch.org/whl/cpu "torch==${TORCH_VERSION}+cpu"; \
    elif [ "${TORCH_INSTALL_FLAVOR}" = "gpu" ]; then \
        python3 -m pip install "torch==${TORCH_VERSION}"; \
    else \
        echo "Unsupported TORCH_INSTALL_FLAVOR=${TORCH_INSTALL_FLAVOR}" >&2; \
        exit 1; \
    fi && \
    python3 -m pip install -r /tmp/requirements.txt && \
    rm -f /tmp/requirements.txt
