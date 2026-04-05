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
