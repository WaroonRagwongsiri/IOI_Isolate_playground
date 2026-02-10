FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
	ca-certificates \
	git \
	build-essential \
	pkg-config \
	libcap-dev \
	libsystemd-dev \
	asciidoc \
	xsltproc \
	docbook-xml \
	docbook-xsl \
	python3 \
	python3-pip \
	pipx \
	&& rm -rf /var/lib/apt/lists/*

RUN pipx ensurepath

RUN pipx install uv

RUN git clone https://github.com/ioi/isolate.git /tmp/isolate \
	&& make -C /tmp/isolate \
	&& make -C /tmp/isolate install \
	&& rm -rf /tmp/isolate

COPY pyproject.toml uv.lock ./

ENV PATH="/root/.local/bin:${PATH}"
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
ENV PATH="/opt/venv/bin:/usr/local/bin:${PATH}"

RUN uv sync --frozen

COPY . .

CMD ["uvicorn", "srcs.main:app", "--host", "0.0.0.0", "--port", "8000"]
