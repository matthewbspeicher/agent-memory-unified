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
