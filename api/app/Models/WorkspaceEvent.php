<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Concerns\HasUuids;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class WorkspaceEvent extends Model
{
    use HasFactory, HasUuids;

    protected $fillable = [
        'workspace_id',
        'event_type',
        'actor_agent_id',
        'payload',
    ];

    protected $casts = [
        'payload' => 'array',
    ];

    // Event type constants
    public const TYPE_MEMORY_CREATED = 'memory.created';

    public const TYPE_MEMORY_UPDATED = 'memory.updated';

    public const TYPE_MEMORY_DELETED = 'memory.deleted';

    public const TYPE_PRESENCE_UPDATED = 'presence.updated';

    public const TYPE_MENTION_CREATED = 'mention.created';

    public const TYPE_MENTION_RESPONDED = 'mention.responded';

    public const TYPE_TASK_CREATED = 'task.created';

    public const TYPE_TASK_UPDATED = 'task.updated';

    public const TYPE_TASK_ASSIGNED = 'task.assigned';

    public const TYPE_TASK_COMPLETED = 'task.completed';

    public const TYPE_AGENT_JOINED = 'agent.joined';

    public function workspace(): BelongsTo
    {
        return $this->belongsTo(Workspace::class);
    }

    public function actor(): BelongsTo
    {
        return $this->belongsTo(Agent::class, 'actor_agent_id');
    }

    /**
     * Dispatch a workspace event.
     */
    public static function dispatch(
        string $workspaceId,
        string $eventType,
        ?string $actorAgentId = null,
        array $payload = []
    ): self {
        return self::create([
            'workspace_id' => $workspaceId,
            'event_type' => $eventType,
            'actor_agent_id' => $actorAgentId,
            'payload' => $payload,
        ]);
    }
}
