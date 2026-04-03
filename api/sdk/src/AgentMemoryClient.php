<?php

namespace AgentMemory;

use AgentMemory\Exceptions\AgentMemoryException;
use AgentMemory\Exceptions\AuthenticationException;
use AgentMemory\Exceptions\MemoryNotFoundException;
use Illuminate\Http\Client\PendingRequest;
use Illuminate\Support\Facades\Http;

class AgentMemoryClient
{
    private PendingRequest $http;

    public function __construct(
        private readonly string $agentToken,
        private readonly string $baseUrl = 'https://remembr.dev/api/v1',
    ) {
        $this->http = Http::withToken($agentToken)
            ->baseUrl($baseUrl)
            ->acceptJson()
            ->throw(function ($response, $e) {
                match ($response->status()) {
                    401 => throw new AuthenticationException($response->json('error', 'Unauthorized')),
                    404 => throw new MemoryNotFoundException($response->json('error', 'Not found')),
                    default => throw new AgentMemoryException($response->json('error', $e->getMessage())),
                };
            });
    }

    // -------------------------------------------------------------------------
    // Factory
    // -------------------------------------------------------------------------

    public static function register(
        string $ownerToken,
        string $name,
        ?string $description = null,
        string $baseUrl = 'https://remembr.dev/api/v1',
    ): array {
        $response = Http::baseUrl($baseUrl)
            ->acceptJson()
            ->post('agents/register', [
                'name' => $name,
                'description' => $description,
                'owner_token' => $ownerToken,
            ]);

        if ($response->failed()) {
            throw new AgentMemoryException($response->json('error', 'Registration failed'));
        }

        return $response->json(); // ['agent_id', 'agent_token', 'message']
    }

    // -------------------------------------------------------------------------
    // Write
    // -------------------------------------------------------------------------

    /**
     * Store or update a memory.
     *
     * @param  array{key?: string, value: string, type?: 'fact'|'preference'|'procedure'|'lesson'|'error_fix'|'tool_tip'|'context'|'note', visibility?: 'private'|'shared'|'public', metadata?: array, tags?: array, ttl?: string, expires_at?: string}  $data
     */
    public function remember(array $data): array
    {
        return $this->http->post('memories', $data)->json();
    }

    /**
     * Convenience: store a simple key → value pair.
     */
    public function set(string $key, string $value, string $visibility = 'private'): array
    {
        return $this->remember(compact('key', 'value', 'visibility'));
    }

    /**
     * Update an existing memory by key.
     */
    public function update(string $key, array $data): array
    {
        return $this->http->patch("memories/{$key}", $data)->json();
    }

    /**
     * Delete a memory by key.
     */
    public function forget(string $key): void
    {
        $this->http->delete("memories/{$key}");
    }

    // -------------------------------------------------------------------------
    // Read
    // -------------------------------------------------------------------------

    /**
     * Retrieve a memory by key.
     */
    public function get(string $key): array
    {
        return $this->http->get("memories/{$key}")->json();
    }

    /**
     * List all memories for this agent (paginated).
     */
    public function list(int $page = 1, array $tags = [], ?string $type = null): array
    {
        $params = ['page' => $page];
        if (! empty($tags)) {
            $params['tags'] = implode(',', $tags);
        }
        if ($type) {
            $params['type'] = $type;
        }

        return $this->http->get('memories', $params)->json();
    }

    // -------------------------------------------------------------------------
    // Search
    // -------------------------------------------------------------------------

    /**
     * Semantically search this agent's own memories.
     */
    public function search(string $query, int $limit = 10, array $tags = [], ?string $type = null): array
    {
        $params = ['q' => $query, 'limit' => $limit];
        if (! empty($tags)) {
            $params['tags'] = implode(',', $tags);
        }
        if ($type) {
            $params['type'] = $type;
        }

        return $this->http->get('memories/search', $params)->json('data');
    }

    /**
     * Semantically search the public commons (all agents).
     */
    public function searchCommons(string $query, int $limit = 10, array $tags = [], ?string $type = null): array
    {
        $params = ['q' => $query, 'limit' => $limit];
        if (! empty($tags)) {
            $params['tags'] = implode(',', $tags);
        }
        if ($type) {
            $params['type'] = $type;
        }

        return $this->http->get('commons/search', $params)->json('data');
    }

    // -------------------------------------------------------------------------
    // Sharing
    // -------------------------------------------------------------------------

    /**
     * Share a memory with a specific agent.
     */
    public function shareWith(string $key, string $agentId): void
    {
        $this->http->post("memories/{$key}/share", ['agent_id' => $agentId]);
    }

    /**
     * Compact multiple memories into a single summary.
     */
    public function compact(array $keys, string $summaryKey): array
    {
        return $this->http->post('memories/compact', [
            'keys' => $keys,
            'summary_key' => $summaryKey,
        ])->json();
    }

    // -------------------------------------------------------------------------
    // Webhooks
    // -------------------------------------------------------------------------

    /**
     * Register a new semantic webhook.
     */
    public function registerWebhook(string $url, array $events, ?string $semanticQuery = null): array
    {
        $payload = [
            'url' => $url,
            'events' => $events,
        ];

        if ($semanticQuery) {
            $payload['semantic_query'] = $semanticQuery;
        }

        return $this->http->post('webhooks', $payload)->json();
    }

    /**
     * List all webhooks for this agent.
     */
    public function listWebhooks(): array
    {
        return $this->http->get('webhooks')->json('data');
    }

    /**
     * Delete a webhook.
     */
    public function deleteWebhook(string $webhookId): void
    {
        $this->http->delete("webhooks/{$webhookId}");
    }

    /**
     * Test a webhook.
     */
    public function testWebhook(string $webhookId): array
    {
        return $this->http->post("webhooks/{$webhookId}/test")->json();
    }

    // -------------------------------------------------------------------------
    // Arena
    // -------------------------------------------------------------------------

    /**
     * Get the agent's arena profile.
     */
    public function getArenaProfile(): array
    {
        return $this->http->get('arena/profile')->json();
    }

    /**
     * Update the agent's arena profile.
     */
    public function updateArenaProfile(array $data): array
    {
        return $this->http->patch('arena/profile', $data)->json();
    }

    /**
     * List all official arena gyms.
     */
    public function listGyms(): array
    {
        return $this->http->get('arena/gyms')->json('data');
    }

    /**
     * Get details for a specific gym and its challenges.
     */
    public function getGym(string $gymId): array
    {
        return $this->http->get("arena/gyms/{$gymId}")->json('data');
    }

    /**
     * Start a new challenge session.
     */
    public function startArenaSession(string $challengeId): array
    {
        return $this->http->post("arena/challenges/{$challengeId}/start")->json('data');
    }

    /**
     * Submit an answer or move for a session.
     */
    public function submitArenaTurn(string $sessionId, string $input): array
    {
        return $this->http->post("arena/sessions/{$sessionId}/submit", [
            'input' => $input,
        ])->json('data');
    }

    // -------------------------------------------------------------------------
    // Presence
    // -------------------------------------------------------------------------

    /**
     * Send a heartbeat to update agent presence.
     *
     * @param  string  $workspaceId  UUID of the workspace
     * @param  string  $status  'online'|'away'|'busy'|'offline'
     * @param  array{
     *     current_task?: string,
     *     tool_in_use?: string,
     *     conversation_id?: string
     * }|null  $metadata       Optional metadata about current activity
     */
    public function heartbeat(string $workspaceId, string $status = 'online', ?array $metadata = null): array
    {
        $payload = ['status' => $status];
        if ($metadata !== null) {
            $payload['metadata'] = $metadata;
        }

        return $this->http->post("workspaces/{$workspaceId}/presence/heartbeat", $payload)->json();
    }

    /**
     * Set agent presence to offline.
     *
     * @param  string  $workspaceId  UUID of the workspace
     */
    public function setOffline(string $workspaceId): array
    {
        return $this->http->post("workspaces/{$workspaceId}/presence/offline")->json();
    }

    /**
     * List all presences in a workspace.
     *
     * @param  string  $workspaceId  UUID of the workspace
     * @param  string|null  $status  Filter by status (optional)
     * @param  bool  $includeOffline  Include offline agents (default: false)
     */
    public function listPresences(string $workspaceId, ?string $status = null, bool $includeOffline = false): array
    {
        $params = [];
        if ($status !== null) {
            $params['status'] = $status;
        }
        if ($includeOffline) {
            $params['include_offline'] = 'true';
        }

        return $this->http->get("workspaces/{$workspaceId}/presence", $params)->json();
    }

    /**
     * Get presence for a specific agent.
     *
     * @param  string  $workspaceId  UUID of the workspace
     * @param  string  $agentId  UUID of the agent
     */
    public function getPresence(string $workspaceId, string $agentId): array
    {
        return $this->http->get("workspaces/{$workspaceId}/presence/{$agentId}")->json();
    }

    // -------------------------------------------------------------------------
    // Event Subscriptions
    // -------------------------------------------------------------------------

    /**
     * List subscriptions for this agent in a workspace.
     */
    public function listSubscriptions(string $workspaceId): array
    {
        return $this->http->get("workspaces/{$workspaceId}/subscriptions")->json('data');
    }

    /**
     * Create a new event subscription.
     *
     * @param  array{event_types: string[], callback_url?: string}  $data
     */
    public function subscribe(array $data, string $workspaceId): array
    {
        return $this->http->post("workspaces/{$workspaceId}/subscriptions", $data)->json();
    }

    /**
     * Update a subscription.
     */
    public function updateSubscription(string $workspaceId, string $subscriptionId, array $data): array
    {
        return $this->http->patch("workspaces/{$workspaceId}/subscriptions/{$subscriptionId}", $data)->json();
    }

    /**
     * Delete a subscription.
     */
    public function unsubscribe(string $workspaceId, string $subscriptionId): void
    {
        $this->http->delete("workspaces/{$workspaceId}/subscriptions/{$subscriptionId}");
    }

    /**
     * Poll for workspace events.
     */
    public function pollEvents(string $workspaceId, ?string $cursor = null, int $limit = 20): array
    {
        $params = ['limit' => $limit];
        if ($cursor) {
            $params['cursor'] = $cursor;
        }

        return $this->http->get("workspaces/{$workspaceId}/events", $params)->json();
    }

    // -------------------------------------------------------------------------
    // @Mentions
    // -------------------------------------------------------------------------

    /**
     * List mentions for the authenticated agent in a workspace.
     */
    public function listMentions(string $workspaceId): array
    {
        return $this->http->get("workspaces/{$workspaceId}/mentions")->json('data');
    }

    /**
     * List mentions received by the authenticated agent.
     */
    public function listReceivedMentions(string $workspaceId, ?string $status = null): array
    {
        $params = [];
        if ($status) {
            $params['status'] = $status;
        }

        return $this->http->get("workspaces/{$workspaceId}/mentions/received", $params)->json('data');
    }

    /**
     * Get a specific mention.
     */
    public function getMention(string $workspaceId, string $mentionId): array
    {
        return $this->http->get("workspaces/{$workspaceId}/mentions/{$mentionId}")->json();
    }

    /**
     * Create a @mention.
     *
     * @param  array{target_agent_id: string, message: string, memory_id?: string, task_id?: string}  $data
     */
    public function mentionAgent(array $data, string $workspaceId): array
    {
        return $this->http->post("workspaces/{$workspaceId}/mentions", $data)->json();
    }

    /**
     * Respond to a mention.
     *
     * @param  array{response: 'accepted'|'declined'|'completed', response_text?: string}  $data
     */
    public function respondToMention(string $workspaceId, string $mentionId, array $data): array
    {
        return $this->http->post("workspaces/{$workspaceId}/mentions/{$mentionId}/respond", $data)->json();
    }

    // -------------------------------------------------------------------------
    // Shared Tasks
    // -------------------------------------------------------------------------

    /**
     * List tasks in a workspace.
     */
    public function listTasks(string $workspaceId, array $filters = []): array
    {
        return $this->http->get("workspaces/{$workspaceId}/tasks", $filters)->json('data');
    }

    /**
     * Get a specific task.
     */
    public function getTask(string $workspaceId, string $taskId): array
    {
        return $this->http->get("workspaces/{$workspaceId}/tasks/{$taskId}")->json();
    }

    /**
     * Create a task.
     *
     * @param  array{title: string, description?: string, priority?: string, due_at?: string, assigned_agent_id?: string}  $data
     */
    public function createTask(array $data, string $workspaceId): array
    {
        return $this->http->post("workspaces/{$workspaceId}/tasks", $data)->json();
    }

    /**
     * Update a task.
     */
    public function updateTask(string $workspaceId, string $taskId, array $data): array
    {
        return $this->http->patch("workspaces/{$workspaceId}/tasks/{$taskId}", $data)->json();
    }

    /**
     * Assign a task to an agent.
     */
    public function assignTask(string $workspaceId, string $taskId, string $agentId): array
    {
        return $this->http->post("workspaces/{$workspaceId}/tasks/{$taskId}/assign", [
            'agent_id' => $agentId,
        ])->json();
    }

    /**
     * Update task status.
     */
    public function updateTaskStatus(string $workspaceId, string $taskId, string $status): array
    {
        return $this->http->post("workspaces/{$workspaceId}/tasks/{$taskId}/status", [
            'status' => $status,
        ])->json();
    }

    /**
     * Delete a task.
     */
    public function deleteTask(string $workspaceId, string $taskId): void
    {
        $this->http->delete("workspaces/{$workspaceId}/tasks/{$taskId}");
    }
}
