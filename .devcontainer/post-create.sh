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

# Set up MCP configuration directory
mkdir -p /home/vscode/.config/claude
chown -R vscode:vscode /home/vscode/.config

# Create MCP configuration
cat > /home/vscode/.config/claude/config.json << 'EOF'
{
  "mcpServers": {
    "puppeteer": {
      "command": "node",
      "args": ["/usr/lib/node_modules/@modelcontextprotocol/server-puppeteer/dist/index.js"],
      "env": {
        "PUPPETEER_EXECUTABLE_PATH": "/usr/bin/google-chrome-stable"
      }
    }
  }
}
EOF

# Set proper permissions
chown vscode:vscode /home/vscode/.config/claude/config.json

# Test Chrome installation
echo "Testing Chrome installation..."
google-chrome-stable --version

# Set permissions on workspace
chown -R vscode:vscode /workspace

echo "Container setup complete!"
echo "MCP Puppeteer server configured and ready to use."