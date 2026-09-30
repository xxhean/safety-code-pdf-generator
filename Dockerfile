ARG PYTHON_IMAGE=m.daocloud.io/docker.io/library/python:3.12-slim
FROM ${PYTHON_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN sed -i 's|http://deb.debian.org|http://mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get -o Acquire::Retries=3 -o Acquire::http::Timeout=30 update \
    && apt-get install -y --no-install-recommends fonts-noto-cjk curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/app
COPY requirements.txt ./
RUN pip install --index-url https://mirrors.aliyun.com/pypi/simple/ -r requirements.txt

COPY app ./app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
