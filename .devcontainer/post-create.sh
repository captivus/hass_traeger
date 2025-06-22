#!/bin/bash

# Set up Git with user's configuration
git config --global user.name "captivus"
git config --global user.email "366332+captivus@users.noreply.github.com"
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