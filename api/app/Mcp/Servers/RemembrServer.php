<?php

namespace App\Mcp\Servers;

use App\Mcp\Tools\DeleteMemoryTool;
use App\Mcp\Tools\GetMemoryTool;
use App\Mcp\Tools\ListMemoriesTool;
use App\Mcp\Tools\SearchCommonsTool;
use App\Mcp\Tools\SearchMemoriesTool;
use App\Mcp\Tools\ShareMemoryTool;
use App\Mcp\Tools\StoreMemoryTool;
use App\Mcp\Tools\UpdateMemoryTool;
use App\Models\Agent;
use Illuminate\Container\Container;
use Illuminate\Http\Request;
use Laravel\Mcp\Server;

class RemembrServer extends Server
{
    protected string $name = 'remembr';

    protected string $version = '0.1.0';

    protected string $instructions = 'Store, search, and retrieve memories for AI agents. Use store_memory to persist information, search_memories for semantic search, list_memories to browse all memories, and search_commons to discover public shared knowledge.';

    protected array $tools = [
        StoreMemoryTool::class,
        UpdateMemoryTool::class,
        SearchMemoriesTool::class,
        GetMemoryTool::class,
        ListMemoriesTool::class,
        DeleteMemoryTool::class,
        SearchCommonsTool::class,
        ShareMemoryTool::class,
    ];

    protected function boot(): void
    {
        $container = Container::getInstance();

        $agent = null;

        // Web transport: agent is set on the HTTP request by the agent.auth middleware
        try {
            /** @var Request $httpRequest */
            $httpRequest = $container->make(Request::class);
            $agent = $httpRequest->attributes->get('agent');
        } catch (\Throwable) {
            // Not in an HTTP context (stdio transport)
        }

        // Stdio transport: resolve from REMEMBR_AGENT_TOKEN env var
        if (! $agent) {
            $token = env('REMEMBR_AGENT_TOKEN');
            if ($token) {
                $agent = Agent::where('api_token', $token)
                    ->where('is_active', true)
                    ->first();
            }
        }

        if ($agent instanceof Agent) {
            $container->instance(Agent::class, $agent);
        }
    }
}
