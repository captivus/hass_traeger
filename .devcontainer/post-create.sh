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
export UV_CACHE_DIR="/home/vscode/.local/share/uv/cache"
export UV_PROJECT_ENVIRONMENT="/home/vscode/.local/share/uv/env"
EOF

# Ensure UV cache directory exists with proper permissions
echo "Setting up UV cache directory..."
mkdir -p /home/vscode/.local/share/uv/cache

# Add Puppeteer MCP server to Claude Code
echo "Configuring Puppeteer MCP server..."
# Run the MCP add command directly (we're already running as vscode user)
claude mcp add puppeteer -s user -- npx -y @modelcontextprotocol/server-puppeteer || echo "Note: MCP server configuration may need to be run after first login"

# Test Chrome installation
echo "Testing Chrome installation..."
google-chrome-stable --version

# Note: We don't need to chown anything since we're already running as vscode user
echo "Workspace permissions should already be correct."

echo "Container setup complete!"
echo "MCP Puppeteer server configured and ready to use."