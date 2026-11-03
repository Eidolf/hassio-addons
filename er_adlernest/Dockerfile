ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base-python:3.12-alpine3.20
FROM ${BUILD_FROM}

ENV LANG=C.UTF-8 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Install runtime tools, CIFS/Samba client, FFmpeg, SQLite, libmagic
RUN apk add --no-cache \
    cifs-utils \
    samba-client \
    ffmpeg \
    sqlite \
    libmagic \
    bash \
    curl \
    jq \
    tzdata \
    gcc \
    musl-dev \
    linux-headers

WORKDIR /app

# Copy backend requirements and install
COPY rootfs/app/backend/requirements.txt /app/backend/
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# Copy root filesystem and application files
COPY rootfs/ /

RUN chmod +x /run.sh

EXPOSE 8098

CMD [ "/run.sh" ]
