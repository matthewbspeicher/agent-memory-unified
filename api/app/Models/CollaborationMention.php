<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Concerns\HasUuids;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class CollaborationMention extends Model
{
    use HasFactory, HasUuids;

    protected $fillable = [
        'workspace_id',
        'agent_id',
        'target_agent_id',
        'status',
        'message',
        'memory_id',
        'task_id',
        'response',
        'responded_at',
    ];

    protected $casts = [
        'responded_at' => 'datetime',
    ];

    // Status constants
    public const STATUS_PENDING = 'pending';

    public const STATUS_ACCEPTED = 'accepted';

    public const STATUS_DECLINED = 'declined';

    public const STATUS_COMPLETED = 'completed';

    public function workspace(): BelongsTo
    {
        return $this->belongsTo(Workspace::class);
    }

    public function sender(): BelongsTo
    {
        return $this->belongsTo(Agent::class, 'agent_id');
    }

    public function target(): BelongsTo
    {
        return $this->belongsTo(Agent::class, 'target_agent_id');
    }

    public function memory(): BelongsTo
    {
        return $this->belongsTo(Memory::class);
    }

    public function task(): BelongsTo
    {
        return $this->belongsTo(WorkspaceTask::class, 'task_id');
    }

    public function respond(string $status, ?string $responseText = null): void
    {
        $this->update([
            'status' => $status,
            'response' => $responseText,
            'responded_at' => now(),
        ]);
    }

    public function isPending(): bool
    {
        return $this->status === self::STATUS_PENDING;
    }
}
