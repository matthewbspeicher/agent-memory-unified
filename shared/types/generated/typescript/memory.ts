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
