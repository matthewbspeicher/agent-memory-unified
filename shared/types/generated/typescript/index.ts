/**
 * AI agent with authentication and permissions
 */
export interface Agent {
    created_at?: Date;
    /**
     * Name of the creating user or system
     */
    creator?: string;
    /**
     * Agent description / neural manifest
     */
    description?: string;
    /**
     * Unique agent identifier
     */
    id: string;
    /**
     * Whether agent can make API calls
     */
    is_active: boolean;
    /**
     * Last activity timestamp
     */
    last_seen_at?: Date | null;
    /**
     * Agent display name
     */
    name: string;
    /**
     * User who owns this agent
     */
    owner_id: string;
    /**
     * Permitted operations (memories:write, trading:execute)
     */
    scopes?: string[];
    /**
     * SHA256 hash of agent token (amc_*)
     */
    token_hash?: string;
    updated_at?: Date;
}

/**
 * Base event structure for Redis Streams
 */
export interface Event {
    /**
     * Event ID (UUID)
     */
    id:        string;
    metadata?: Metadata;
    /**
     * Event-specific data
     */
    payload: { [key: string]: any };
    /**
     * Source service ('api', 'trading')
     */
    source:    Source;
    timestamp: Date;
    /**
     * Event type (trade.opened, memory.created, etc.)
     */
    type: string;
    /**
     * Event schema version (e.g., '1.0')
     */
    version: string;
}

export interface Metadata {
    /**
     * Parent event ID that caused this
     */
    causation_id?: string;
    /**
     * Request trace ID
     */
    correlation_id?: string;
    [property: string]: any;
}

/**
 * Source service ('api', 'trading')
 */
export enum Source {
    API = "api",
    Trading = "trading",
}

/**
 * Knowledge record stored by an agent (MemClaw-compatible)
 */
export interface Memory {
    agent_id:    string;
    created_at?: Date;
    /**
     * Auto-computed based on memory_type: fact=120, episode=45, decision=180, preference=365,
     * task=30, semantic=120, intention=60, plan=60, commitment=120, action=30, outcome=90,
     * cancellation=14, rule=365
     */
    decay_days?: number;
    /**
     * 1536-dim vector (optional in DTOs)
     */
    embedding?: number[];
    /**
     * Computed from created_at + decay_days
     */
    expires_at?: Date | null;
    id:          string;
    /**
     * Legacy importance (deprecated, use weight)
     */
    importance?: number;
    /**
     * Memory classification (MemClaw 13-type taxonomy)
     */
    memory_type?: MemoryType;
    /**
     * Arbitrary key-value metadata
     */
    metadata?: { [key: string]: any };
    /**
     * Memory lifecycle status
     */
    status?: MemoryStatus;
    /**
     * Short summary for quick scanning
     */
    summary?:    string;
    tags?:       string[];
    updated_at?: Date;
    /**
     * Memory content
     */
    value: string;
    /**
     * Legacy visibility (deprecated, use visibility_scope)
     */
    visibility: Visibility;
    /**
     * Visibility scope: agent-only, team-shared, org-wide
     */
    visibility_scope?: VisibilityScope;
    /**
     * Importance weight (0-1), replaces legacy importance field
     */
    weight?: number;
}

/**
 * Memory classification (MemClaw 13-type taxonomy)
 */
export enum MemoryType {
    Action = "action",
    Cancellation = "cancellation",
    Commitment = "commitment",
    Decision = "decision",
    Episode = "episode",
    Fact = "fact",
    Intention = "intention",
    Outcome = "outcome",
    Plan = "plan",
    Preference = "preference",
    Rule = "rule",
    Semantic = "semantic",
    Task = "task",
}

/**
 * Memory lifecycle status
 */
export enum MemoryStatus {
    Active = "active",
    Archived = "archived",
    Cancelled = "cancelled",
    Confirmed = "confirmed",
    Conflicted = "conflicted",
    Deleted = "deleted",
    Outdated = "outdated",
    Pending = "pending",
}

/**
 * Legacy visibility (deprecated, use visibility_scope)
 */
export enum Visibility {
    Private = "private",
    Public = "public",
}

/**
 * Visibility scope: agent-only, team-shared, org-wide
 */
export enum VisibilityScope {
    ScopeAgent = "scope_agent",
    ScopeOrg = "scope_org",
    ScopeTeam = "scope_team",
}

/**
 * Simplified trade DTO for API responses (subset of tracked_positions table)
 */
export interface Trade {
    /**
     * Agent UUID (internal reference)
     */
    agent_id?: string;
    /**
     * Display name of agent that created trade
     */
    agent_name: string;
    /**
     * Memory explaining why trade was taken
     */
    decision_memory_id?: null | string;
    /**
     * Stored as TEXT in DB for precision
     */
    entry_price: string;
    /**
     * Number of shares/contracts
     */
    entry_quantity: number;
    entry_time:     Date;
    /**
     * Exit price (TEXT for precision)
     */
    exit_price?: null | string;
    exit_time?:  Date | null;
    /**
     * Trade ID (SERIAL in Postgres)
     */
    id: number;
    /**
     * Additional strategy-specific data
     */
    metadata?: { [key: string]: any };
    /**
     * Memory analyzing trade result
     */
    outcome_memory_id?: null | string;
    /**
     * Paper trading vs real money
     */
    paper?: boolean;
    /**
     * Profit/loss in dollars
     */
    pnl?: number | null;
    /**
     * Profit/loss as percentage
     */
    pnl_percent?: number | null;
    side:         Side;
    status:       TradeStatus;
    /**
     * Strategy that generated this trade
     */
    strategy?: string;
    /**
     * Trading symbol (AAPL, BTC, etc.)
     */
    symbol: string;
}

export enum Side {
    Long = "long",
    Short = "short",
}

export enum TradeStatus {
    Cancelled = "cancelled",
    Closed = "closed",
    Open = "open",
}
