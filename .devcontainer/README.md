# Claude Code DevContainer Setup

This container is configured for Claude Code to work in "YOLO mode" with full development capabilities.

## Features

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

## MCP Configuration

The Puppeteer MCP server is automatically configured and ready to use. Claude Code can access it via the standard MCP interface.

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