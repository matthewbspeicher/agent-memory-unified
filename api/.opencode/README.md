# OpenCode Configuration

This directory contains OpenCode configuration files for the Agent Memory Commons project.

## Directory Structure

```
.opencode/
├── plugins/           # Custom plugins
│   └── notifications.js   # macOS notifications
├── agents/            # Custom agent definitions
│   └── memory-expert.md   # Memory management agent
├── commands/          # Custom commands
│   └── memory-store.md    # Store memory command
├── instructions/      # Project-specific instructions
│   └── project-context.md # Project context for AI
├── tools/             # Custom tools
│   └── memory-api.js      # Memory API integration
├── themes/            # Custom themes (empty)
├── skills/            # Custom skills (empty)
└── README.md          # This file
```

## Key Files

### `opencode.json` (in project root)
Main configuration file with:
- Model settings (Claude Sonnet 4.5, Haiku 4.5)
- MCP servers (GitHub, Sentry, Context7, Grep, Agent Memory)
- Custom agents (code-reviewer, planner, memory-manager)
- Tool permissions and formatters
- Plugin and instruction paths

### `plugins/notifications.js`
Sends macOS notifications for:
- Session completion
- Session errors
- Session creation

### `agents/memory-expert.md`
Specialized agent for managing Agent Memory Commons:
- Store, search, and manage memories
- Integrate with MCP server
- Handle visibility and tagging

### `commands/memory-store.md`
Custom command for storing memories:
- `/memory-store <content> [visibility] [tags]`
- Calls memory API
- Provides feedback

### `tools/memory-api.js`
Custom tools for Agent Memory Commons API:
- `memory-search`: Search memories
- `memory-store`: Store new memories
- `memory-get`: Retrieve specific memory

## Setup

1. Set environment variables:
   ```bash
   export AGENT_MEMORY_TOKEN="your-api-token"
   export ANTHROPIC_API_KEY="your-anthropic-key"
   export OPENAI_API_KEY="your-openai-key"
   ```

2. Enable MCP servers in `opencode.json`:
   - Set `enabled: true` for servers you want to use
   - Configure OAuth for GitHub and Sentry

3. Start OpenCode:
   ```bash
   cd /path/to/agent-memory
   opencode
   ```

## Usage

### Store a memory
```
/memory-store "I prefer dark mode for interfaces" private preferences,ui
```

### Search memories
```
Find memories about my coding preferences
```

### Use MCP servers
```
Show me recent Sentry issues using sentry
Search GitHub for authentication patterns using gh_grep
```

### Code review
```
Switch to code-reviewer agent and review my changes
```

## Customization

- Add more plugins in `plugins/`
- Define more agents in `agents/` or `opencode.json`
- Add custom commands in `commands/`
- Add project instructions in `instructions/`
- Create custom tools in `tools/`

## More Information

- OpenCode docs: https://opencode.ai/docs
- MCP servers: https://opencode.ai/docs/mcp-servers
- Plugins: https://opencode.ai/docs/plugins
- Agent Memory Commons: https://remembr.dev