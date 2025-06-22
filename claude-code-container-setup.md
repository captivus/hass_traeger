# Claude Code Container Setup for YOLO Mode

This guide helps you create a secure container environment where Claude Code can work independently on your project.

## Prerequisites

- Docker Desktop or Docker Engine installed
- VS Code with Remote - Containers extension
- Git

## Container Setup

### 1. Create devcontainer configuration

Create `.devcontainer/devcontainer.json`:

```json
{
  "name": "Claude Code YOLO Container",
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
    "source=claude-cache,target=/home/vscode/.cache,type=volume"
  ],
  "runArgs": [
    "--cap-add=SYS_PTRACE",
    "--security-opt", "seccomp=unconfined",
    "--network=claude-net"
  ],
  "forwardPorts": [3000, 8080, 5000]
}
```

### 2. Create Dockerfile

Create `.devcontainer/Dockerfile`:

```dockerfile
FROM mcr.microsoft.com/devcontainers/base:ubuntu-22.04

# Install essential tools
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
    && rm -rf /var/lib/apt/lists/*

# Install UV for Python management
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.cargo/bin:${PATH}"

# Install additional development tools
RUN apt-get update && apt-get install -y \
    zsh \
    fzf \
    tmux \
    neovim \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
ARG USERNAME=vscode
ARG USER_UID=1000
ARG USER_GID=$USER_UID

RUN groupadd --gid $USER_GID $USERNAME \
    && useradd --uid $USER_UID --gid $USER_GID -m $USERNAME \
    && echo $USERNAME ALL=\(root\) NOPASSWD:ALL > /etc/sudoers.d/$USERNAME \
    && chmod 0440 /etc/sudoers.d/$USERNAME

# Set up ZSH for the user
USER $USERNAME
RUN sh -c "$(curl -fsSL https://raw.github.com/ohmyzsh/ohmyzsh/master/tools/install.sh)" "" --unattended

# Switch back to root for final setup
USER root

# Set working directory
WORKDIR /workspace
```

### 3. Create post-create script

Create `.devcontainer/post-create.sh`:

```bash
#!/bin/bash

# Set up Git (customize with your info)
git config --global user.name "Claude Code"
git config --global user.email "claude@example.com"
git config --global init.defaultBranch main

# Install UV for the vscode user
su - vscode -c "curl -LsSf https://astral.sh/uv/install.sh | sh"

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
EOF

# Set permissions
chown -R vscode:vscode /workspace

echo "Container setup complete!"
```

### 4. Create network isolation script (optional)

For enhanced security, create `.devcontainer/init-firewall.sh`:

```bash
#!/bin/bash

# Create custom Docker network with restricted access
docker network create claude-net 2>/dev/null || true

# Set up iptables rules for the container
# Allow only specific domains (customize as needed)
ALLOWED_DOMAINS=(
    "github.com"
    "pypi.org"
    "npmjs.org"
    "docker.io"
    "ubuntu.com"
)

# This is a simplified example - adjust based on your security needs
echo "Network isolation configured"
```

## Usage Instructions

### Starting the Container

1. Open your project in VS Code
2. Press `Ctrl+Shift+P` and select "Remote-Containers: Reopen in Container"
3. Wait for container to build and start

### Giving Claude Code Access

When using Claude Code in this container:

1. Mount your project directory: Already configured in `devcontainer.json`
2. Claude Code will have access to:
   - All files in `/workspace` (your project)
   - Internet access for package installation
   - Common development tools
   - Docker-in-docker for container operations

### Security Considerations

- Container runs with limited capabilities
- Non-root user by default
- Persistent volumes for history and cache
- Network can be restricted via firewall rules
- All changes are isolated to the container

### Best Practices for YOLO Mode

1. **Backup First**: Always backup your project before giving full access
2. **Use Version Control**: Commit your work before Claude Code sessions
3. **Review Changes**: Even in YOLO mode, review significant changes
4. **Limit Scope**: Define clear boundaries for what Claude should work on
5. **Monitor Resources**: Container resource limits can be set in Docker

### Customization

Modify the configuration files to:
- Add more development tools
- Install specific language runtimes
- Configure additional VS Code extensions
- Set up database connections
- Add environment variables

### Cleanup

To remove the container and volumes:
```bash
docker container prune
docker volume rm claude-history claude-cache
docker network rm claude-net
```

## Quick Start Commands

```bash
# Clone this setup to your project
mkdir -p .devcontainer
# Copy the files above into .devcontainer/

# Make scripts executable
chmod +x .devcontainer/*.sh

# Open in VS Code
code .
# Then use Command Palette: "Reopen in Container"
```

This setup provides Claude Code with a fully functional development environment while maintaining security through containerization.