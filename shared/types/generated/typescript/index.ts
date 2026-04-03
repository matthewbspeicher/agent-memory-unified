export interface AgentSchema {
    schema:               string;
    id:                   string;
    type:                 string;
    title:                string;
    description:          string;
    properties:           AgentSchemaProperties;
    required:             string[];
    additionalProperties: boolean;
}

export interface AgentSchemaProperties {
    id:        ID;
    name:      Name;
    tokenHash: Name;
    isActive:  IsActive;
    scopes:    Scopes;
    createdAt: CreatedAt;
    updatedAt: CreatedAt;
}

export interface CreatedAt {
    type:   Type;
    format: Format;
}

export enum Format {
    DateTime = "date-time",
    UUID = "uuid",
}

export enum Type {
    String = "string",
}

export interface ID {
    type:        Type;
    format:      Format;
    description: string;
}

export interface IsActive {
    type:        string;
    description: string;
}

export interface Name {
    type:        Type;
    maxLength:   number;
    description: string;
}

export interface Scopes {
    type:        string;
    items:       ExitPrice;
    description: string;
}

export interface ExitPrice {
    type: string;
}

export interface EventSchema {
    schema:               string;
    id:                   string;
    type:                 string;
    title:                string;
    description:          string;
    properties:           EventSchemaProperties;
    required:             string[];
    additionalProperties: boolean;
}

export interface EventSchemaProperties {
    id:        IsActive;
    type:      IsActive;
    version:   Version;
    timestamp: CreatedAt;
    source:    Source;
    payload:   IsActive;
    metadata:  Metadata;
}

export interface Metadata {
    type:       string;
    properties: MetadataProperties;
}

export interface MetadataProperties {
    correlationID: IsActive;
    causationID:   IsActive;
}

export interface Source {
    type:        Type;
    enum:        string[];
    description: string;
}

export interface Version {
    type:        Type;
    default:     string;
    description: string;
}

export interface MemorySchema {
    schema:               string;
    id:                   string;
    type:                 string;
    title:                string;
    description:          string;
    properties:           MemorySchemaProperties;
    required:             string[];
    additionalProperties: boolean;
}

export interface MemorySchemaProperties {
    id:         CreatedAt;
    agentID:    CreatedAt;
    value:      IsActive;
    type:       Source;
    summary:    Name;
    tags:       Tags;
    visibility: Visibility;
    importance: Importance;
    createdAt:  CreatedAt;
}

export interface Importance {
    type:    string;
    minimum: number;
    maximum: number;
    default: number;
}

export interface Tags {
    type:  string;
    items: ExitPrice;
}

export interface Visibility {
    type:    Type;
    enum:    string[];
    default: string;
}

export interface TradeSchema {
    schema:               string;
    id:                   string;
    type:                 string;
    title:                string;
    description:          string;
    properties:           TradeSchemaProperties;
    required:             string[];
    additionalProperties: boolean;
}

export interface TradeSchemaProperties {
    id:               CreatedAt;
    agentID:          CreatedAt;
    ticker:           Name;
    direction:        Direction;
    entryPrice:       IsActive;
    quantity:         IsActive;
    entryAt:          CreatedAt;
    exitAt:           CreatedAt;
    exitPrice:        ExitPrice;
    status:           Visibility;
    pnl:              IsActive;
    pnlPercent:       IsActive;
    strategy:         IsActive;
    paper:            Paper;
    decisionMemoryID: ID;
    outcomeMemoryID:  ID;
    metadata:         IsActive;
}

export interface Direction {
    type: Type;
    enum: string[];
}

export interface Paper {
    type:        string;
    description: string;
    default:     boolean;
}
