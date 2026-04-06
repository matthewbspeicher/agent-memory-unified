/**
 * AI agent with authentication and permissions
 */
export interface Agent {
    created_at?: Date;
    /**
     * Unique agent identifier
     */
    id: string;
    /**
     * Whether agent can make API calls
     */
    is_active: boolean;
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
 * Knowledge record stored by an agent
 */
export interface Memory {
    agent_id:    string;
    created_at?: Date;
    /**
     * 1536-dim vector (optional in DTOs)
     */
    embedding?:  number[];
    id:          string;
    importance?: number;
    /**
     * Short summary for quick scanning
     */
    summary?: string;
    tags?:    string[];
    /**
     * Memory classification
     */
    type?: Type;
    /**
     * Memory content
     */
    value:      string;
    visibility: Visibility;
}

/**
 * Memory classification
 */
export enum Type {
    Fact = "fact",
    Lesson = "lesson",
    Note = "note",
    Preference = "preference",
    Procedure = "procedure",
}

export enum Visibility {
    Private = "private",
    Public = "public",
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
    status:       Status;
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

export enum Status {
    Cancelled = "cancelled",
    Closed = "closed",
    Open = "open",
}
