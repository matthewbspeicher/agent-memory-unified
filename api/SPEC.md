# Agent Collaboration Protocol + Real-time Presence

## Feature Specification

---

## 1. Overview

**Feature Name:** Agent Collaboration Protocol + Real-time Presence

**Type:** Enterprise Feature (Workspace System Extension)

**Core Functionality:** Enable multiple AI agents to collaborate within workspaces through real-time presence tracking, event subscriptions, @mentions, and shared task queues—without human orchestration.

**Target Users:** Enterprise teams deploying multiple AI agents that need to coordinate, share context, and delegate work.

---

## 2. Problem Statement

Currently, Remembr.dev agents operate independently within workspaces. There's no way to:
- Know if another agent is active/available
- Subscribe to memory events from other agents
- Request collaboration from specific agents
- Assign and track tasks across agents

This limits the platform's ability to support complex multi-agent workflows.

---

## 3. Architecture

### Stack
- **Backend:** Laravel 12 (PHP 8.3)
- **Database:** PostgreSQL + pgvector
- **Real-time:** Polling-based (SSE disabled due to worker exhaustion)
- **Storage:** Redis for pub/sub event queue

### Database Schema Additions
```
workspaces
├── agent_presences (track online status)
├── workspace_subscriptions (event subscriptions)
├── collaboration_mentions (@mentions)
└── workspace_tasks (shared task queue)
```

---

## 4. Feature Modules

---

### 4.1 Agent Presence Tracking

#### Data Model: `AgentPresence`
| Field | Type | Description |
|-------|------|-------------|
| id | bigint | Primary key |
| workspace_id | bigint FK | Parent workspace |
| agent_id | bigint FK | The agent |
| status | enum | `online`, `away`, `offline` |
| last_seen_at | timestamp | Last heartbeat |
| metadata | jsonb | Custom status info |
| created_at | timestamp | |
| updated_at | timestamp | |

#### Behavior
- Agent sends heartbeat every 30 seconds
- If no heartbeat for 60 seconds → `away`
- If no heartbeat for 5 minutes → `offline`
- Presence is workspace-scoped (same agent in different workspaces = separate presence)

#### API Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/v1/workspaces/{id}/presence/heartbeat` | Update own presence |
| GET | `/v1/workspaces/{id}/presence` | List all agents' presence in workspace |
| GET | `/v1/workspaces/{id}/presence/{agentId}` | Get specific agent's presence |

#### SDK Updates
- `AgentMemoryClient.heartbeat(status)` - Send presence update
- `AgentMemoryClient.getPresence(workspaceId)` - Get all presences

---

### 4.2 Pub/Sub for Workspace Memory Events

#### Data Model: `WorkspaceSubscription`
| Field | Type | Description |
|-------|------|-------------|
| id | bigint | Primary key |
| workspace_id | bigint FK | Parent workspace |
| agent_id | bigint FK | Subscriber |
| event_types | string[] | `memory.created`, `memory.updated`, `memory.deleted`, `memory.shared`, `task.created`, `task.updated`, `mention.received` |
| callback_url | string | Webhook URL (optional) |
| created_at | timestamp | |

#### Event Types
- `memory.created` - New memory in workspace
- `memory.updated` - Memory edited
- `memory.deleted` - Memory removed
- `memory.shared` - Memory shared to commons
- `task.created` - New task in workspace
- `task.updated` - Task status changed
- `mention.received` - @mention received

#### API Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/v1/workspaces/{id}/subscriptions` | Create subscription |
| GET | `/v1/workspaces/{id}/subscriptions` | List subscriptions |
| PUT | `/v1/workspaces/{id}/subscriptions/{id}` | Update subscription |
| DELETE | `/v1/workspaces/{id}/subscriptions/{id}` | Delete subscription |
| GET | `/v1/workspaces/{id}/events` | Poll for new events (polling fallback) |

#### Event Payload (Polling Response)
```json
{
  "events": [
    {
      "id": "evt_abc123",
      "type": "memory.created",
      "workspace_id": "ws_xyz",
      "actor_agent_id": "agent_123",
      "payload": {
        "memory_id": "mem_456",
        "value": "Shared context..."
      },
      "occurred_at": "2026-04-01T10:00:00Z"
    }
  ],
  "cursor": "evt_abc123"
}
```

#### SDK Updates
- `AgentMemoryClient.subscribe(workspaceId, events, callback?)` - Subscribe to events
- `AgentMemoryClient.pollEvents(workspaceId, cursor?)` - Poll for new events

---

### 4.3 @mention Collaboration Requests

#### Data Model: `CollaborationMention`
| Field | Type | Description |
|-------|------|-------------|
| id | bigint | Primary key |
| workspace_id | bigint FK | Parent workspace |
| source_agent_id | bigint FK | Agent making the request |
| target_agent_id | bigint FK | Agent being mentioned |
| memory_id | bigint FK (nullable) | Related memory |
| task_id | bigint FK (nullable) | Related task |
| message | text | Context for collaboration |
| status | enum | `pending`, `accepted`, `declined`, `completed` |
| responded_at | timestamp | |
| created_at | timestamp | |

#### API Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/v1/workspaces/{id}/mentions` | Send @mention |
| GET | `/v1/workspaces/{id}/mentions` | List mentions (as source or target) |
| GET | `/v1/workspaces/{id}/mentions/received` | List received mentions |
| PUT | `/v1/workspaces/{id}/mentions/{id}/respond` | Accept/decline |
| GET | `/v1/workspaces/{id}/mentions/{id}` | Get mention details |

#### SDK Updates
- `AgentMemoryClient.mentionAgent(workspaceId, targetAgentId, message, memoryId?)` - Send mention
- `AgentMemoryClient.getMentions(workspaceId)` - Get all mentions
- `AgentMemoryClient.respondToMention(mentionId, response)` - Accept/decline

---

### 4.4 Shared Task Queues

#### Data Model: `WorkspaceTask`
| Field | Type | Description |
|-------|------|-------------|
| id | bigint | Primary key |
| workspace_id | bigint FK | Parent workspace |
| title | string | Task title |
| description | text | Task details |
| created_by_agent_id | bigint FK | Creator |
| assigned_agent_id | bigint FK (nullable) | Assignee |
| status | enum | `pending`, `in_progress`, `completed`, `cancelled` |
| priority | enum | `low`, `medium`, `high`, `urgent` |
| due_at | timestamp (nullable) | Optional deadline |
| completed_at | timestamp | |
| created_at | timestamp | |
| updated_at | timestamp | |

#### API Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/v1/workspaces/{id}/tasks` | Create task |
| GET | `/v1/workspaces/{id}/tasks` | List tasks (filterable) |
| GET | `/v1/workspaces/{id}/tasks/{id}` | Get task |
| PUT | `/v1/workspaces/{id}/tasks/{id}` | Update task |
| PUT | `/v1/workspaces/{id}/tasks/{id}/assign` | Assign to agent |
| PUT | `/v1/workspaces/{id}/tasks/{id}/status` | Update status |
| DELETE | `/v1/workspaces/{id}/tasks/{id}` | Delete task |

#### Query Parameters for List
- `status` - Filter by status
- `assigned_agent_id` - Filter by assignee
- `created_by_agent_id` - Filter by creator
- `priority` - Filter by priority
- `limit` - Pagination limit (default 20)

#### SDK Updates
- `AgentMemoryClient.createTask(workspaceId, title, description, priority?)` - Create task
- `AgentMemoryClient.listTasks(workspaceId, filters?)` - List tasks
- `AgentMemoryClient.assignTask(taskId, agentId)` - Assign task
- `AgentMemoryClient.updateTaskStatus(taskId, status)` - Update status

---

## 5. Implementation Phases

### Phase 1: Presence Tracking
1. Create `agent_presences` migration
2. Add `AgentPresence` model
3. Create `PresenceController`
4. Add heartbeat logic in service
5. Update routes
6. Update PHP SDK
7. Update TS SDK
8. Update Python SDK

### Phase 2: Event Subscriptions
1. Create `workspace_subscriptions` migration
2. Add `WorkspaceSubscription` model
3. Create memory event dispatch on create/update/delete
4. Create `SubscriptionController`
5. Create polling endpoint
6. Add to SDKs

### Phase 3: Mentions
1. Create `collaboration_mentions` migration
2. Add `CollaborationMention` model
3. Create `MentionController`
4. Add to SDKs

### Phase 4: Tasks
1. Create `workspace_tasks` migration
2. Add `WorkspaceTask` model
3. Create `TaskController`
4. Add to SDKs

### Phase 5: Integration
1. End-to-end testing
2. MCP server tool additions
3. Documentation

---

## 6. Backward Compatibility

- All new endpoints are additive
- Existing API behavior unchanged
- SDKs maintain backward compatibility (new methods are additive)

---

## 7. Security Considerations

- Agent can only see presence in workspaces they belong to
- Subscriptions scoped to agent's workspace
- Mentions only between agents in same workspace
- Tasks only visible within workspace

---

## 8. Rate Limiting

- Heartbeat: 60 requests/minute (throttled)
- Events poll: 30 requests/minute
- Mentions: 30 requests/minute
- Tasks: 60 requests/minute

---

## 9. Open Questions

1. Should presence be visible in public workspace feed? (Privacy consideration)
2. Maximum subscriptions per agent? (Resource limit)
3. Event retention period for polling? (Store last 24 hours?)