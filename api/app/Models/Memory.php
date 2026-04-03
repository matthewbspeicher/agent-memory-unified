<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Builder;
use Illuminate\Database\Eloquent\Concerns\HasUuids;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\BelongsToMany;

class Memory extends Model
{
    use HasFactory, HasUuids;

    const TYPES = [
        'fact', 'preference', 'procedure', 'lesson',
        'error_fix', 'tool_tip', 'context', 'note',
    ];

    protected $fillable = [
        'agent_id',
        'workspace_id',
        'key',
        'value',
        'summary',
        'type',
        'category',
        'embedding',
        'metadata',
        'visibility',
        'importance',
        'confidence',
        'access_count',
        'useful_count',
        'last_accessed_at',
        'expires_at',
    ];

    protected $casts = [
        'metadata' => 'array',
        'importance' => 'integer',
        'confidence' => 'float',
        'access_count' => 'integer',
        'useful_count' => 'integer',
        'last_accessed_at' => 'datetime',
        'expires_at' => 'datetime',
    ];

    // -------------------------------------------------------------------------
    // Relationships
    // -------------------------------------------------------------------------

    public function agent(): BelongsTo
    {
        return $this->belongsTo(Agent::class);
    }

    public function workspace(): BelongsTo
    {
        return $this->belongsTo(Workspace::class);
    }

    public function sharedWith(): BelongsToMany
    {
        return $this->belongsToMany(Agent::class, 'memory_shares')
            ->withPivot('created_at');
    }

    public function relatedTo(): BelongsToMany
    {
        return $this->belongsToMany(Memory::class, 'memory_relations', 'source_id', 'target_id')
            ->withPivot('type')
            ->withTimestamps();
    }

    public function relatedFrom(): BelongsToMany
    {
        return $this->belongsToMany(Memory::class, 'memory_relations', 'target_id', 'source_id')
            ->withPivot('type')
            ->withTimestamps();
    }

    // -------------------------------------------------------------------------
    // Scopes
    // -------------------------------------------------------------------------

    public function scopeNotExpired(Builder $query): Builder
    {
        return $query->where(function ($q) {
            $q->whereNull('expires_at')->orWhere('expires_at', '>', now());
        });
    }

    public function scopePublic(Builder $query): Builder
    {
        return $query->where('visibility', 'public');
    }

    public function scopeOfType(Builder $query, string $type): Builder
    {
        return $query->where('type', $type);
    }

    public function scopeInCategory(Builder $query, string $category): Builder
    {
        return $query->where('category', $category);
    }

    public function scopeAccessibleBy(Builder $query, Agent $agent): Builder
    {
        return $query->where(function ($q) use ($agent) {
            // Own memories
            $q->where('agent_id', $agent->id)
              // Explicitly shared with this agent
                ->orWhereHas('sharedWith', fn ($sq) => $sq->where('agent_id', $agent->id))
              // Shared in a workspace this agent is a member of
                ->orWhereIn('workspace_id', $agent->workspaces()->select('workspaces.id'));
        });
    }

    public function scopeVisibleTo(Builder $query, Agent $agent): Builder
    {
        return $query->where(function ($q) use ($agent) {
            // Own memories
            $q->where('agent_id', $agent->id)
              // Public memories
                ->orWhere('visibility', 'public')
              // Explicitly shared with this agent
                ->orWhereHas('sharedWith', fn ($sq) => $sq->where('agent_id', $agent->id))
              // Shared in a workspace this agent is a member of
                ->orWhereIn('workspace_id', $agent->workspaces()->select('workspaces.id'));
        });
    }

    public function scopeWithTags(Builder $query, array $tags): Builder
    {
        foreach ($tags as $tag) {
            $query->whereJsonContains('metadata->tags', $tag);
        }

        return $query;
    }

    // -------------------------------------------------------------------------
    // Semantic search (pgvector cosine similarity)
    // -------------------------------------------------------------------------

    public function scopeSemanticSearch(Builder $query, array $embedding, int $limit = 10): Builder
    {
        $vector = '['.implode(',', $embedding).']';

        return $query
            ->selectRaw('*, 1 - (embedding <=> ?) AS similarity', [$vector])
            ->whereNotNull('embedding')
            ->orderByRaw('embedding <=> ?', [$vector])
            ->limit($limit);
    }

    // -------------------------------------------------------------------------
    // Keyword search (PostgreSQL full-text search)
    // -------------------------------------------------------------------------

    public function scopeKeywordSearch(Builder $query, string $searchTerm, int $limit = 10): Builder
    {
        // Replace spaces with | for to_tsquery (OR search) to improve recall
        // Ranking will handle relevance
        $searchTerm = trim($searchTerm);

        if (empty($searchTerm)) {
            return $query;
        }

        return $query
            ->selectRaw('*, ts_rank(search_vector, websearch_to_tsquery(\'english\', ?)) AS rank', [$searchTerm])
            ->whereRaw("search_vector @@ websearch_to_tsquery('english', ?)", [$searchTerm])
            ->orderByRaw('rank DESC')
            ->limit($limit);
    }

    // -------------------------------------------------------------------------
    // Helpers
    // -------------------------------------------------------------------------

    public function isExpired(): bool
    {
        return $this->expires_at !== null && $this->expires_at->isPast();
    }
}
