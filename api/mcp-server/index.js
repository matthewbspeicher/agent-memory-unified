#!/usr/bin/env node

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "@modelcontextprotocol/sdk/deps.js";

const BASE_URL = process.env.REMEMBR_BASE_URL || "https://remembr.dev";
const TOKEN = process.env.REMEMBR_AGENT_TOKEN;

if (!TOKEN) {
  console.error("REMEMBR_AGENT_TOKEN environment variable is required");
  process.exit(1);
}

const headers = {
  Authorization: `Bearer ${TOKEN}`,
  "Content-Type": "application/json",
  Accept: "application/json",
};

async function api(method, path, body) {
  const opts = { method, headers };
  if (body) opts.body = JSON.stringify(body);
  
  try {
    const res = await fetch(`${BASE_URL}/api/v1${path}`, opts);
    let data;
    
    // Check if the response has JSON content
    const contentType = res.headers.get("content-type");
    if (contentType && contentType.includes("application/json")) {
      data = await res.json();
    } else {
      data = { message: await res.text() || `API error ${res.status}` };
    }
    
    if (!res.ok) throw new Error(data.message || `API error ${res.status}`);
    return data;
  } catch (error) {
    if (error.message.startsWith("API error") || error.message.includes("failed") || error.message.includes("Failed to fetch") || error.message.includes("fetch failed")) {
       throw error;
    }
    throw new Error(`Network error communicating with Remembr API: ${error.message}`);
  }
}

const server = new McpServer({
  name: "remembr",
  version: "1.0.0",
});

// --- Tools ---

server.tool(
  "store_memory",
  "Store a memory for the authenticated agent",
  {
    value: z.string().describe("The memory content to store"),
    key: z.string().optional().describe("Optional unique key for this memory"),
    visibility: z.enum(["private", "shared", "public"]).default("private").describe("Memory visibility"),
    type: z.enum(['fact', 'preference', 'procedure', 'lesson', 'error_fix', 'tool_tip', 'context', 'note']).default('note').describe('Memory type. fact=objective knowledge, preference=user/agent prefs, procedure=how-to steps, lesson=experiential learning, error_fix=problem+solution, tool_tip=API/tool patterns, context=session state, note=general (default)'),
    category: z.string().max(100).optional().describe("Optional category for organizing memories (e.g., 'preferences', 'task-history', 'skills')"),
    metadata: z.record(z.any()).optional().describe("Optional metadata object for categorization"),
    expires_at: z.string().optional().describe("Optional ISO 8601 expiry timestamp"),
    ttl: z.string().optional().describe("Optional shorthand time-to-live (e.g., '24h', '7d', '30m')"),
    tags: z.array(z.string()).max(10).optional().describe("Optional array of tags (max 10)"),
  },
  async ({ value, key, visibility, type, category, metadata, expires_at, ttl, tags }) => {
    const body = { value, visibility };
    if (key) body.key = key;
    if (category) body.category = category;
    if (metadata) body.metadata = metadata;
    if (expires_at) body.expires_at = expires_at;
    if (ttl) body.ttl = ttl;
    if (tags) body.tags = tags;
    if (type) body.type = type;
    const result = await api("POST", "/memories", body);
    return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
  }
);

server.tool(
  "update_memory",
  "Update an existing memory by key",
  {
    key: z.string().describe("The memory key to update"),
    value: z.string().optional().describe("The new memory content"),
    visibility: z.enum(["private", "shared", "public"]).optional().describe("New visibility setting"),
    type: z.enum(['fact', 'preference', 'procedure', 'lesson', 'error_fix', 'tool_tip', 'context', 'note']).optional().describe('Memory type. fact=objective knowledge, preference=user/agent prefs, procedure=how-to steps, lesson=experiential learning, error_fix=problem+solution, tool_tip=API/tool patterns, context=session state, note=general (default)'),
    category: z.string().max(100).optional().describe("New category for this memory"),
    metadata: z.record(z.any()).optional().describe("New metadata object (will replace existing)"),
    expires_at: z.string().optional().describe("New ISO 8601 expiry timestamp"),
    ttl: z.string().optional().describe("New shorthand time-to-live (e.g., '24h', '7d', '30m')"),
    tags: z.array(z.string()).max(10).optional().describe("New array of tags (max 10)"),
  },
  async ({ key, value, visibility, type, category, metadata, expires_at, ttl, tags }) => {
    const body = {};
    if (value !== undefined) body.value = value;
    if (visibility !== undefined) body.visibility = visibility;
    if (type !== undefined) body.type = type;
    if (category !== undefined) body.category = category;
    if (metadata !== undefined) body.metadata = metadata;
    if (expires_at !== undefined) body.expires_at = expires_at;
    if (ttl !== undefined) body.ttl = ttl;
    if (tags !== undefined) body.tags = tags;
    
    if (Object.keys(body).length === 0) {
      throw new Error("Must provide at least one field to update");
    }
    
    const result = await api("PATCH", `/memories/${encodeURIComponent(key)}`, body);
    return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
  }
);

server.tool(
  "search_memories",
  "Semantic search across your own memories. Use detail='summary' to reduce token usage.",
  {
    q: z.string().describe("Natural language search query"),
    limit: z.number().default(10).describe("Max results to return"),
    tags: z.string().optional().describe("Comma-separated list of tags to filter by"),
    type: z.enum(['fact', 'preference', 'procedure', 'lesson', 'error_fix', 'tool_tip', 'context', 'note']).optional().describe('Filter results to this memory type only'),
    category: z.string().optional().describe("Filter results to this category only"),
    detail: z.enum(['full', 'summary']).default('full').describe("'summary' returns short summaries instead of full values (saves tokens)"),
  },
  async ({ q, limit, tags, type, category, detail }) => {
    const tagsParam = tags ? `&tags=${encodeURIComponent(tags)}` : '';
    const typeParam = type ? `&type=${encodeURIComponent(type)}` : '';
    const catParam = category ? `&category=${encodeURIComponent(category)}` : '';
    const detailParam = detail ? `&detail=${encodeURIComponent(detail)}` : '';
    const result = await api("GET", `/memories/search?q=${encodeURIComponent(q)}&limit=${limit}${tagsParam}${typeParam}${catParam}${detailParam}`);
    return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
  }
);

server.tool(
  "get_memory",
  "Retrieve a specific memory by key",
  {
    key: z.string().describe("The memory key to retrieve"),
  },
  async ({ key }) => {
    const result = await api("GET", `/memories/${encodeURIComponent(key)}`);
    return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
  }
);

server.tool(
  "list_memories",
  "List all memories for the authenticated agent. Use detail='summary' to reduce token usage.",
  {
    page: z.number().default(1).describe("Page number"),
    tags: z.string().optional().describe("Comma-separated list of tags to filter by"),
    type: z.enum(['fact', 'preference', 'procedure', 'lesson', 'error_fix', 'tool_tip', 'context', 'note']).optional().describe('Filter results to this memory type only'),
    category: z.string().optional().describe("Filter results to this category only"),
    detail: z.enum(['full', 'summary']).default('full').describe("'summary' returns short summaries instead of full values (saves tokens)"),
  },
  async ({ page, tags, type, category, detail }) => {
    const tagsParam = tags ? `&tags=${encodeURIComponent(tags)}` : '';
    const typeParam = type ? `&type=${encodeURIComponent(type)}` : '';
    const catParam = category ? `&category=${encodeURIComponent(category)}` : '';
    const detailParam = detail ? `&detail=${encodeURIComponent(detail)}` : '';
    const result = await api("GET", `/memories?page=${page}${tagsParam}${typeParam}${catParam}${detailParam}`);
    return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
  }
);

server.tool(
  "delete_memory",
  "Delete a memory by key",
  {
    key: z.string().describe("The memory key to delete"),
  },
  async ({ key }) => {
    const result = await api("DELETE", `/memories/${encodeURIComponent(key)}`);
    return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
  }
);

server.tool(
  "search_commons",
  "Semantic search across all public memories from all agents. Use detail='summary' to reduce token usage.",
  {
    q: z.string().describe("Natural language search query"),
    limit: z.number().default(10).describe("Max results to return"),
    tags: z.string().optional().describe("Comma-separated list of tags to filter by"),
    type: z.enum(['fact', 'preference', 'procedure', 'lesson', 'error_fix', 'tool_tip', 'context', 'note']).optional().describe('Filter results to this memory type only'),
    category: z.string().optional().describe("Filter results to this category only"),
    detail: z.enum(['full', 'summary']).default('full').describe("'summary' returns short summaries instead of full values (saves tokens)"),
  },
  async ({ q, limit, tags, type, category, detail }) => {
    const tagsParam = tags ? `&tags=${encodeURIComponent(tags)}` : '';
    const typeParam = type ? `&type=${encodeURIComponent(type)}` : '';
    const catParam = category ? `&category=${encodeURIComponent(category)}` : '';
    const detailParam = detail ? `&detail=${encodeURIComponent(detail)}` : '';
    const result = await api("GET", `/commons/search?q=${encodeURIComponent(q)}&limit=${limit}${tagsParam}${typeParam}${catParam}${detailParam}`);
    return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
  }
);

server.tool(
  "share_memory",
  "Share a memory with another agent by their agent ID",
  {
    key: z.string().describe("Memory key to share"),
    agent_id: z.string().describe("ID of the agent to share with"),
  },
  async ({ key, agent_id }) => {
    const data = await api("POST", `/memories/${encodeURIComponent(key)}/share`, { agent_id });
    return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
  }
);

server.tool(
  "arena_get_profile",
  "Retrieve your agent's Battle Arena profile, including bio, tags, and Elo rating",
  {},
  async () => {
    const result = await api("GET", "/arena/profile");
    return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
  }
);

server.tool(
  "arena_update_profile",
  "Update your agent's Battle Arena profile",
  {
    bio: z.string().optional().describe("Your persona description or backstory"),
    personality_tags: z.array(z.string()).max(20).optional().describe("Array of personality trait tags (max 20)"),
    avatar_url: z.string().optional().describe("Optional URL to your avatar image"),
  },
  async ({ bio, personality_tags, avatar_url }) => {
    const body = {};
    if (bio !== undefined) body.bio = bio;
    if (personality_tags !== undefined) body.personality_tags = personality_tags;
    if (avatar_url !== undefined) body.avatar_url = avatar_url;
    
    if (Object.keys(body).length === 0) {
      throw new Error("Must provide at least one field to update");
    }
    
    const result = await api("PATCH", "/arena/profile", body);
    return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
  }
);

server.tool(
  "arena_list_gyms",
  "List available official and community Gyms to battle in",
  {},
  async () => {
    const result = await api("GET", "/arena/gyms");
    return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
  }
);

server.tool(
  "arena_play_match",
  "The primary interface for playing in the Battle Arena. Use this to queue for matches, draft challenges, and submit turns. The server will hold the connection open until it is your turn to act, so you don't need to poll.",
  {
    action: z.enum(["queue", "draft_veto", "submit_turn"]).describe("The action to take in the arena"),
    match_id: z.string().optional().describe("The ID of the match (required for draft_veto and submit_turn)"),
    payload: z.string().optional().describe("The challenge ID to veto, or your JSON/String solution for the current turn"),
  },
  async ({ action, match_id, payload }) => {
    if (action === "queue") {
        const result = await api("POST", "/arena/queue");
        // In a full implementation, this would start a polling loop against a /status endpoint
        // until the match is found, then return the draft state.
        // For now, we return the immediate API response.
        return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    }
    
    if (!match_id) {
        throw new Error("match_id is required for actions other than 'queue'");
    }

    if (action === "draft_veto") {
        if (!payload) throw new Error("payload (challenge_id to veto) is required for draft_veto");
        const result = await api("POST", `/arena/matches/${encodeURIComponent(match_id)}/veto`, { challenge_id: payload });
        // Again, this would ideally poll until the opponent vetoes.
        return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    }

    if (action === "submit_turn") {
        if (!payload) throw new Error("payload (your move/solution) is required for submit_turn");
        
        let parsedPayload = payload;
        try {
            // Try to parse as JSON if possible, otherwise send as string
            parsedPayload = JSON.parse(payload);
        } catch (e) {
            // It's a plain string, leave it
        }

        const result = await api("POST", `/arena/matches/${encodeURIComponent(match_id)}/turn`, { payload: parsedPayload });
        // Polling logic would go here to wait for opponent/validator response.
        return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    }
    
    throw new Error(`Unknown action: ${action}`);
  }
);

server.tool(
  "extract_session",
  "Extract durable memories from a conversation transcript. The AI will analyze the transcript and automatically create structured memories from facts, preferences, procedures, and lessons learned.",
  {
    transcript: z.string().min(20).max(50000).describe("The conversation transcript to extract memories from"),
    category: z.string().max(100).optional().describe("Default category for extracted memories (default: 'session-extraction')"),
    visibility: z.enum(["private", "shared", "public"]).default("private").describe("Visibility for extracted memories"),
  },
  async ({ transcript, category, visibility }) => {
    const body = { transcript, visibility };
    if (category) body.category = category;
    const result = await api("POST", "/sessions/extract", body);
    return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
  }
);

server.tool(
  "memory_feedback",
  "Provide feedback on whether a memory was useful. This helps improve search ranking over time — useful memories get boosted in future results.",
  {
    key: z.string().describe("The memory key to provide feedback on"),
    useful: z.boolean().describe("Whether the memory was useful (true) or not (false)"),
  },
  async ({ key, useful }) => {
    const result = await api("POST", `/memories/${encodeURIComponent(key)}/feedback`, { useful });
    return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
  }
);

server.tool(
  "trading_record_execution",
  "Record an entry or exit execution for a trade.",
  {
    ticker: z.string().describe("The ticker symbol"),
    direction: z.enum(["long", "short"]).describe("Trade direction"),
    entry_price: z.number().describe("Entry price"),
    quantity: z.number().describe("Quantity of the asset"),
    entry_at: z.string().describe("ISO8601 timestamp of the trade entry"),
    paper: z.boolean().default(true).describe("Whether this is a paper trade"),
    strategy: z.string().optional().describe("Optional strategy name"),
    confidence: z.number().optional().describe("Optional confidence score (0-1)"),
    parent_trade_id: z.string().optional().describe("Optional parent trade ID for closing/partial exit"),
    decision_memory_id: z.string().optional().describe("Optional UUID of the memory containing the decision reasoning"),
    outcome_memory_id: z.string().optional().describe("Optional UUID of the memory containing the trade outcome/lesson"),
  },
  async ({ ticker, direction, entry_price, quantity, entry_at, paper, strategy, confidence, parent_trade_id, decision_memory_id, outcome_memory_id }) => {
    const body = { ticker, direction, entry_price, quantity, entry_at, paper };
    if (strategy !== undefined) body.strategy = strategy;
    if (confidence !== undefined) body.confidence = confidence;
    if (parent_trade_id !== undefined) body.parent_trade_id = parent_trade_id;
    if (decision_memory_id !== undefined) body.decision_memory_id = decision_memory_id;
    if (outcome_memory_id !== undefined) body.outcome_memory_id = outcome_memory_id;
    const result = await api("POST", "/trading/trades", body);
    return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
  }
);

server.tool(
  "trading_get_open_positions",
  "Retrieve the agent's current open trading positions.",
  {
    paper: z.boolean().default(true).describe("Whether to fetch paper trading positions"),
  },
  async ({ paper }) => {
    const result = await api("GET", `/trading/positions?paper=${paper}`);
    return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
  }
);

server.tool(
  "trading_get_performance",
  "Retrieve the agent's aggregate trading statistics.",
  {
    paper: z.boolean().default(true).describe("Whether to fetch paper trading stats"),
  },
  async ({ paper }) => {
    const result = await api("GET", `/trading/stats?paper=${paper}`);
    return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
  }
);

server.tool(
  "trading_get_equity_curve",
  "Retrieve the time-series cumulative PnL for charting.",
  {
    paper: z.boolean().default(true).describe("Whether to fetch paper trading equity curve"),
  },
  async ({ paper }) => {
    const result = await api("GET", `/trading/stats/equity-curve?paper=${paper}`);
    return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
  }
);

// --- Start ---

const transport = new StdioServerTransport();
await server.connect(transport);
