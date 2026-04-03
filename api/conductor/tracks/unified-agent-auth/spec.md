# Specification: Unified Agent Authentication (UAA)

## Overview
Autonomous agents on the `agent-memory` platform (e.g., `stock-trading-api`) need the ability to interact with the system as first-class entities. This includes both API-driven tasks (backend) and interacting with UI components or dashboards (frontend). Currently, agents are restricted to specific API endpoints and lack the session context required for standard web routes (Inertia, etc.).

This refactor introduces a unified authentication mechanism that allows agents to authenticate using their `amc_...` tokens across all system routes, while maintaining clear identity as an autonomous agent acting on behalf of a human owner.

## Goals
1. **Agent as Authenticatable**: The `Agent` model must implement Laravel's `Authenticatable` interface.
2. **Multi-Guard Support**: Standard web routes should support both `session` (for humans) and `agent` (for autonomous agents) authentication.
3. **Agent Context Service**: A centralized service to manage the current acting entity (User vs. Agent).
4. **Token-to-Session Bridge**: A mechanism to establish a request context for agents on web routes without requiring a traditional browser session.

## Requirements

### 1. Model Updates (`Agent.php`)
- Implement `Illuminate\Contracts\Auth\Authenticatable`.
- Provide `getAuthIdentifierName()`, `getAuthIdentifier()`, `getAuthPassword()`, `getRememberToken()`, `setRememberToken()`, `getRememberTokenName()`.
- Since Agents use tokens, `getAuthPassword()` should return an empty string or null.

### 2. Guard Configuration (`config/auth.php`)
- Define a new guard `agent` with driver `token` (or custom).
- Define a new provider `agents` for the `Agent` model.

### 3. Middleware Integration
- **`AuthenticateAgent`**: Refactor to use Laravel's guard system. It should check for `amc_...` tokens and authenticate the `agent` guard.
- **CSRF Bypass**: Authenticated agents (via token) should be exempted from CSRF checks as they are using explicit token-based auth rather than session-based auth.

### 4. Inertia State Sharing (`HandleInertiaRequests.php`)
- Include `actingAgent` in the shared `auth` object if an agent is authenticated.
- Example shared state:
  ```json
  {
    "auth": {
      "user": { ... },
      "agent": { ... } // Only if acting as an agent
    }
  }
  ```

### 5. Access Control
- All existing `Auth::user()` calls must remain functional for human users.
- For agent-authenticated requests, `Auth::user()` will return the `Agent` instance (if using the `agent` guard).
- A common helper `ActingEntity::owner()` should return the `User` (owner) regardless of whether a User or Agent is authenticated.

## Migration Path
1. Update the `Agent` model.
2. Register the new guard and provider.
3. Update the `AuthenticateAgent` middleware.
4. Update `routes/web.php` to include the `AuthenticateAgent` or a multi-guard `auth` check.
5. Update Inertia middleware to share the context.

## Security Considerations
- **Token Integrity**: Agent tokens (`amc_...`) must remain highly secure.
- **Permissions**: Agents must only act on behalf of their owner and within the owner's plan limits.
- **Scope**: Ensure that agents cannot accidentally modify owner-only resources (like billing details) unless explicitly permitted.
