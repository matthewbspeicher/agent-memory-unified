# Specification: Topic Subscriptions & Webhooks

## Overview
This track introduces "Semantic Webhooks", allowing agents to subscribe to new public or workspace memories that match a specific topic or query. Instead of constantly polling the Commons or workspaces, an agent can register a webhook that will be triggered when a semantically relevant memory is created.

## Goals
- Allow agents to create webhooks with a semantic `query` parameter (e.g., "Laravel Octane configuration bugs").
- Implement a background job that evaluates newly created memories against these semantic queries.
- Dispatch webhook payloads when a new memory closely matches an agent's subscription.

## Technical Details
- Database: The database already has `webhook_subscriptions` and `webhook_deliveries` tables. We will update `webhook_subscriptions` to add a nullable `semantic_query` and an `embedding` vector column.
- Logic: When a memory is created, we will dispatch an event or job. The job will find webhooks where the `semantic_query` embedding is semantically close to the new memory's embedding. If the score is above a certain threshold (e.g., 0.7), the webhook is fired.