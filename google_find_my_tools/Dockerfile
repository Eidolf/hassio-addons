FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget \
    git \
    gnupg     unzip \
    xvfb \
    libxi6     libnss3 \
    libasound2 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libgbm1 \
    libx11-xcb1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxi6 \
    libxrandr2 \
    libxrender1 \
    libxss1 \
    libxtst6 \
    ca-certificates \
    fonts-liberation \
    libnspr4     lsb-release \
    xdg-utils \
    fluxbox \
    x11vnc \
    net-tools \
    python3-websockify \
    python3-numpy \
    xterm \
    --no-install-recommends

# Install noVNC
RUN git clone https://github.com/novnc/noVNC.git /opt/novnc && \
    git clone https://github.com/novnc/websockify /opt/novnc/utils/websockify && \
    ln -s /opt/novnc/vnc.html /opt/novnc/index.html

# Install Google Chrome Beta
RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-linux-signing-key.gpg && \
    sh -c 'echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-linux-signing-key.gpg] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list' && \
    apt-get update && \
    apt-get install -y google-chrome-beta && \
    rm -rf /var/lib/apt/lists/*

# Symlink google-chrome-beta
RUN ln -sf /usr/bin/google-chrome-beta /usr/bin/google-chrome

WORKDIR /app

# Clone the repository
RUN git clone https://github.com/Eidolf/GoogleFindMyTools.git .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy test script for GCM debugging
COPY test_gcm.py /app/test_gcm.py
RUN pip install aiohttp

# Copy run script
COPY run.sh /run.sh
RUN chmod +x /run.sh

# Set environment variables
ENV PYTHONUNBUFFERED=1

CMD ["/run.sh"]
