FROM mcr.microsoft.com/devcontainers/base:ubuntu-22.04

# Install essential tools and Chrome dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    curl \
    wget \
    zip \
    unzip \
    jq \
    ripgrep \
    fd-find \
    bat \
    htop \
    net-tools \
    iputils-ping \
    dnsutils \
    postgresql-client \
    redis-tools \
    # Chrome dependencies
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcairo2 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libpango-1.0-0 \
    libx11-6 \
    libxcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# Install Google Chrome Stable
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Install UV for Python management  
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    mv /root/.local/bin/uv* /usr/local/bin/ && \
    chmod +x /usr/local/bin/uv*

# Install additional development tools
RUN apt-get update && apt-get install -y \
    zsh \
    fzf \
    tmux \
    neovim \
    && rm -rf /var/lib/apt/lists/*

# Create MCP directories
RUN mkdir -p /home/vscode/.config/claude && \
    chown -R vscode:vscode /home/vscode/.config

# Set working directory
WORKDIR /workspace