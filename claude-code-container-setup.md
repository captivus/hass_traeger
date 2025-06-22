# Building a Claude Code DevContainer: A Complete Guide to YOLO Mode Development

## Introduction

This comprehensive guide will walk you through building a VS Code DevContainer that enables Claude Code to work autonomously on your projects. We'll cover everything from the initial setup to troubleshooting common issues, sharing real-world lessons learned along the way.

### What is YOLO Mode?

YOLO (You Only Live Once) mode refers to running Claude Code with the `--dangerously-skip-permissions` flag, allowing it to execute commands without asking for confirmation each time. While this sounds risky, when properly containerized, it's actually a safe and efficient way to let Claude Code work independently on your projects.

### Why Use a DevContainer?

DevContainers provide:
- **Isolation**: All changes happen inside the container
- **Consistency**: Same environment across all developers
- **Safety**: Your host system remains untouched
- **Persistence**: Work is saved through volume mounts
- **Reproducibility**: Easy to rebuild if something goes wrong

## Prerequisites

Before we begin, ensure you have:
- **Docker Desktop** installed and running
- **VS Code** with the **Dev Containers** extension (formerly Remote - Containers)
- **Git** for version control
- A project you want Claude Code to work on

## Step 1: Understanding the Architecture

Our DevContainer will have several layers:

```
┌─────────────────────────────────────┐
│         Your Host System            │
├─────────────────────────────────────┤
│         Docker Desktop              │
├─────────────────────────────────────┤
│      DevContainer (Ubuntu)          │
│  ┌─────────────────────────────┐   │
│  │   Claude Code + MCP Server   │   │
│  ├─────────────────────────────┤   │
│  │   Development Tools:         │   │
│  │   - Node.js, Python, UV      │   │
│  │   - Chrome, Puppeteer        │   │
│  │   - Git, ripgrep, etc.      │   │
│  └─────────────────────────────┘   │
└─────────────────────────────────────┘
```

## Step 2: Creating the DevContainer Configuration

### 2.1 Directory Structure

First, create the `.devcontainer` directory in your project root:

```bash
mkdir -p .devcontainer
cd .devcontainer
```

### 2.2 The devcontainer.json File

Create `.devcontainer/devcontainer.json`:

```json
{
  "name": "Claude Code YOLO Container with MCP",
  "build": {
    "dockerfile": "Dockerfile",
    "context": ".."
  },
  "features": {
    "ghcr.io/devcontainers/features/node:1": {
      "version": "20"
    },
    "ghcr.io/devcontainers/features/python:1": {
      "version": "3.11"
    },
    "ghcr.io/devcontainers/features/docker-in-docker:2": {}
  },
  "customizations": {
    "vscode": {
      "extensions": [
        "ms-python.python",
        "ms-vscode.cpptools",
        "rust-lang.rust-analyzer"
      ]
    }
  },
  "postCreateCommand": "bash .devcontainer/post-create.sh",
  "remoteUser": "vscode",
  "mounts": [
    "source=${localWorkspaceFolder},target=/workspace,type=bind",
    "source=claude-history,target=/home/vscode/.zsh_history,type=volume",
    "source=claude-cache,target=/home/vscode/.cache,type=volume",
    "source=claude-mcp-config,target=/home/vscode/.config/claude,type=volume"
  ],
  "runArgs": [
    "--cap-add=SYS_PTRACE",
    "--security-opt", "seccomp=unconfined",
    "--cap-add=SYS_ADMIN",
    "--shm-size=2gb"
  ],
  "forwardPorts": [3000, 8080, 5000, 9222],
  "containerEnv": {
    "PUPPETEER_SKIP_CHROMIUM_DOWNLOAD": "false",
    "PUPPETEER_EXECUTABLE_PATH": "/usr/bin/google-chrome-stable",
    "UV_CACHE_DIR": "/home/vscode/.cache/uv",
    "UV_PROJECT_ENVIRONMENT": "/home/vscode/.cache/uv/env"
  },
  "remoteEnv": {
    "ANTHROPIC_API_KEY": "${localEnv:ANTHROPIC_API_KEY:}"
  }
}
```

**Key Points:**
- **Features**: We use official devcontainer features for Node.js, Python, and Docker-in-Docker
- **Mounts**: Your project is bind-mounted, while caches use named volumes for persistence
- **Environment Variables**: Critical for Puppeteer and UV to work correctly
- **Security**: Additional capabilities needed for Chrome and debugging

### Common Issue #1: Build Order Matters

Initially, we tried installing everything in the Dockerfile, including npm packages. This failed because:
- The base image is built first
- Then devcontainer features are applied
- Node.js wasn't available during the Dockerfile build

**Solution**: Move runtime installations to the post-create script.

## Step 3: Creating the Dockerfile

Create `.devcontainer/Dockerfile`:

```dockerfile
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
```

### Common Issue #2: Base Image Already Has User

We initially tried to create the `vscode` user, but the base image already includes it. This caused:
```
groupadd: group 'vscode' already exists
```

**Solution**: The `mcr.microsoft.com/devcontainers/base` image already has the vscode user configured. Don't recreate it!

### Common Issue #3: Chrome Dependencies

Chrome requires many system libraries. Missing any of these causes Puppeteer to fail with cryptic errors.

**Solution**: Install all Chrome dependencies explicitly (the long list in the Dockerfile).

## Step 4: Creating the Post-Create Script

Create `.devcontainer/post-create.sh`:

```bash
#!/bin/bash

# Set up Git with user's configuration
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"
git config --global init.defaultBranch main

# Install Node.js packages globally (Node.js is now available from features)
echo "Installing MCP Puppeteer server and TypeScript tools..."
npm install -g \
    @modelcontextprotocol/server-puppeteer \
    typescript \
    ts-node

# Install Claude Code CLI
echo "Installing Claude Code..."
npm install -g @anthropic-ai/claude-code

# Create useful aliases
cat >> /home/vscode/.zshrc << 'EOF'
# Claude Code aliases
alias ll='ls -la'
alias gs='git status'
alias gd='git diff'
alias gc='git commit'
alias gp='git push'
alias docker-clean='docker system prune -af'

# UV aliases
alias uvr='uv run'
alias uva='uv add'
alias uvs='uv sync'

# Safety aliases
alias rm='rm -i'
alias cp='cp -i'
alias mv='mv -i'

# Claude Code alias
alias cc='claude'

# UV environment variables
export UV_CACHE_DIR="/home/vscode/.cache/uv"
export UV_PROJECT_ENVIRONMENT="/home/vscode/.cache/uv/env"
EOF

# Fix UV cache permissions for vscode user
echo "Setting up UV cache and permissions..."
mkdir -p /home/vscode/.cache/uv
chown -R vscode:vscode /home/vscode/.cache
chmod -R 755 /home/vscode/.cache

# Add Puppeteer MCP server to Claude Code
echo "Adding Puppeteer MCP server to Claude Code..."
su - vscode -c "claude mcp add puppeteer -s user -- npx -y @modelcontextprotocol/server-puppeteer" || true

# Test Chrome installation
echo "Testing Chrome installation..."
google-chrome-stable --version

# Set permissions on workspace
chown -R vscode:vscode /workspace

echo "Container setup complete!"
echo "MCP Puppeteer server configured and ready to use."
```

Make it executable:
```bash
chmod +x .devcontainer/post-create.sh
```

### Common Issue #4: UV Permission Errors

UV was installed as root but runs as the vscode user, causing:
```
error: failed to create directory `/home/vscode/.cache/uv`: Permission denied (os error 13)
```

**Solution**: 
1. Create the cache directory with proper ownership
2. Set UV environment variables
3. Export them in the shell profile

### Common Issue #5: MCP Server Configuration

We initially tried to manually create MCP config files, but this doesn't work. Claude Code manages its own configuration.

**Solution**: Use the official CLI command:
```bash
claude mcp add puppeteer -s user -- npx -y @modelcontextprotocol/server-puppeteer
```

## Step 5: Building and Running the Container

### 5.1 Open Your Project in VS Code

```bash
code /path/to/your/project
```

### 5.2 Reopen in Container

1. Press `Ctrl+Shift+P` (or `Cmd+Shift+P` on Mac)
2. Type "Dev Containers: Reopen in Container"
3. Select it and wait for the build (first time takes 5-10 minutes)

### 5.3 Verify Everything Works

Once inside the container, test:

```bash
# Check Claude Code
claude --version

# Check MCP servers
claude mcp list

# Check Chrome
google-chrome-stable --version

# Check UV
uv --version
```

## Step 6: Using Claude Code in YOLO Mode

### 6.1 Authentication

You have two options:

**Option 1: Claude Account Login (Recommended for Pro/Team)**
```bash
claude login
```

**Option 2: API Key**
```bash
export ANTHROPIC_API_KEY="your-api-key"
```

### 6.2 Running in YOLO Mode

To run without permission prompts:
```bash
claude --dangerously-skip-permissions
```

Or with an initial task:
```bash
claude --dangerously-skip-permissions "implement the new feature we discussed"
```

### 6.3 Using MCP Puppeteer

In Claude Code, you can now use commands like:
```
/mcp puppeteer_navigate https://example.com
/mcp puppeteer_screenshot example.png
```

## Step 7: Best Practices and Tips

### 7.1 Git Workflow

Always commit your work before letting Claude Code make changes:
```bash
git add .
git commit -m "Checkpoint before Claude Code session"
```

### 7.2 Resource Limits

You can add resource limits to your container:
```json
"runArgs": [
  "--memory=8g",
  "--cpus=4"
]
```

### 7.3 Database Persistence

For projects with databases, ensure they're in the workspace:
```
project/
├── .devcontainer/
├── src/
└── data/
    └── database.db  # This persists between container rebuilds
```

### 7.4 Custom Tools

Add project-specific tools to the Dockerfile:
```dockerfile
# Example: Install Rust
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"
```

## Troubleshooting Common Issues

### Issue: "No MCP servers configured"

**Symptom**: Running `/mcp` in Claude Code shows no servers.

**Solution**: The MCP server must be added after Claude Code is authenticated. Run:
```bash
claude mcp add puppeteer -s user -- npx -y @modelcontextprotocol/server-puppeteer
```

### Issue: Container Fails to Build

**Symptom**: Build errors during container creation.

**Solution**: 
1. Check Docker Desktop is running
2. Ensure you have enough disk space
3. Try clearing Docker cache: `docker system prune -a`

### Issue: Permission Denied Errors

**Symptom**: Various permission errors when running commands.

**Solution**: Ensure all paths are properly owned:
```bash
sudo chown -R vscode:vscode /workspace
sudo chown -R vscode:vscode /home/vscode
```

### Issue: Chrome/Puppeteer Won't Start

**Symptom**: Puppeteer fails with "Failed to launch the browser process".

**Solution**: 
1. Verify Chrome is installed: `google-chrome-stable --version`
2. Check the executable path is set correctly
3. Ensure all Chrome dependencies are installed

## Advanced Configuration

### Adding More MCP Servers

You can add additional MCP servers:
```bash
# Filesystem server
claude mcp add filesystem -s user -- npx -y @modelcontextprotocol/server-filesystem

# GitHub server
claude mcp add github -s user -- npx -y @modelcontextprotocol/server-github
```

### Project-Specific Configuration

Create a `.mcp.json` in your project root:
```json
{
  "servers": {
    "project-specific": {
      "command": "node",
      "args": ["./scripts/mcp-server.js"]
    }
  }
}
```

### Network Restrictions

For enhanced security, you can restrict network access:
```bash
# In post-create.sh
# Block all outbound traffic except specific domains
sudo iptables -A OUTPUT -d github.com -j ACCEPT
sudo iptables -A OUTPUT -d pypi.org -j ACCEPT
sudo iptables -A OUTPUT -j DROP
```

## Conclusion

Building a proper DevContainer for Claude Code involves understanding:
1. The DevContainer build lifecycle
2. User permissions and ownership
3. MCP server configuration
4. Environment variable management
5. Tool installation timing

With this setup, you can safely run Claude Code in YOLO mode, letting it work independently on your projects while maintaining full control and safety through containerization.

### Final Checklist

- [ ] DevContainer builds successfully
- [ ] Claude Code is installed and runnable
- [ ] MCP Puppeteer server is available (`/mcp` shows it)
- [ ] Chrome works for browser automation
- [ ] UV works without permission errors
- [ ] Git is configured with your credentials
- [ ] Your project files persist between container rebuilds
- [ ] You can run `claude --dangerously-skip-permissions` successfully

Remember: The container is your safety net. Even in YOLO mode, all changes are isolated, and you can always rebuild if needed. Happy coding with Claude Code!

## Additional Resources

- [Claude Code Documentation](https://docs.anthropic.com/en/docs/claude-code/overview)
- [VS Code Dev Containers](https://code.visualstudio.com/docs/devcontainers/containers)
- [Model Context Protocol (MCP)](https://docs.anthropic.com/en/docs/claude-code/mcp)
- [Docker Best Practices](https://docs.docker.com/develop/dev-best-practices/)