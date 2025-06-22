# Claude Code DevContainer Setup

This container is configured for Claude Code to work in "YOLO mode" with full development capabilities.

## Features

- **Claude Code**: AI coding assistant pre-installed (`claude` or `cc` command)
- **MCP Puppeteer Server**: Pre-configured for web automation
- **Chrome Browser**: Installed for headless/headful browser automation
- **Python with UV**: Modern Python package management
- **Node.js 20**: For JavaScript/TypeScript development
- **Docker-in-Docker**: Container operations support
- **Development Tools**: git, ripgrep, fzf, and more

## Quick Start

1. Open this project in VS Code
2. Install "Dev Containers" extension if not already installed
3. Press `Ctrl+Shift+P` and select "Dev Containers: Reopen in Container"
4. Wait for container to build (first time takes ~5 minutes)

## Claude Code Setup

After the container starts, choose one authentication method:

### Option 1: Claude Account Login (Recommended for Claude Pro/Team)
1. Run: `claude login`
2. Follow the prompts to authenticate with your Claude account
3. Run Claude Code: `claude` or `cc` (alias)

### Option 2: API Key
1. Set your Anthropic API key: `export ANTHROPIC_API_KEY="your-api-key"`
2. Run Claude Code: `claude` or `cc` (alias)

Claude Code will have full access to the workspace with pre-approved commands

## Running Claude Code Without Confirmations

To have Claude Code execute commands without asking for permission each time:

### Option 1: Skip All Permissions (Use with Caution)
```bash
# Skip all permission prompts
claude --dangerously-skip-permissions
# or
cc --dangerously-skip-permissions

# With an initial task
claude --dangerously-skip-permissions "implement the missing prediction features"
```

### Option 2: Pre-approve Specific Tools
```bash
# Allow specific tools without prompts
claude --allowedTools bash,read,write,edit

# Combine with skip permissions for full automation
claude --dangerously-skip-permissions --allowedTools bash,read,write,edit
```

### Interactive Mode Features:
- Use `Ctrl+L` to clear screen
- Use Up/Down arrows for command history
- Use `Ctrl+C` to cancel current operation
- Use `Ctrl+D` to exit

**Note**: The `--dangerously-skip-permissions` flag is safe in this container since all changes are isolated and your work is persisted through bind mounts

## MCP Configuration

The Puppeteer MCP server is automatically added during container setup using:
```bash
claude mcp add puppeteer -s user -- npx -y @modelcontextprotocol/server-puppeteer
```

To verify MCP servers are available:
```bash
claude mcp list
```

Or in Claude Code, type `/mcp` to see available servers.

## Pre-approved Commands

The following commands run without approval prompts:
- Basic navigation: `ls`, `cd`, `pwd`
- Git operations: `git status`, `git diff`, `git log`
- Package management: `npm install/run`, `uv run/add/sync`
- Language runtimes: `python`, `node`
- Docker: `docker ps`, `docker logs`

## Ports

The following ports are automatically forwarded:
- 3000: Common web dev server
- 8080: Alternative web server
- 5000: Python Flask default
- 9222: Chrome DevTools Protocol

## Security Notes

- Container runs with limited privileges
- Non-root user (`vscode`) by default
- Network access to standard package registries
- All changes isolated to container

## Customization

To add more tools or change configuration, modify:
- `.devcontainer/Dockerfile`: System packages and tools
- `.devcontainer/devcontainer.json`: VS Code settings and mounts
- `.devcontainer/post-create.sh`: User-specific setup
- `.devcontainer/claude-code-settings.json`: Claude Code permissions