<?php

use App\Mcp\Servers\RemembrServer;
use Laravel\Mcp\Facades\Mcp;

// Web transport — HTTP-based MCP clients (Claude.ai, Cursor, etc.)
Mcp::web('/mcp/remembr', RemembrServer::class)
    ->middleware('agent.auth');

// Stdio transport — CLI clients (Claude Code)
// Usage: REMEMBR_AGENT_TOKEN=amc_xxx php artisan mcp:run remembr
Mcp::local('remembr', RemembrServer::class);
