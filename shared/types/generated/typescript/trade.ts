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
