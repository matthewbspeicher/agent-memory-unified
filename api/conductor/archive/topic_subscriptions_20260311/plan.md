# Implementation Plan: Topic Subscriptions & Webhooks

## Phase 1: Database and Model Updates [checkpoint: c67a16a]
- [x] Task: Update Webhook Subscriptions Table [commit: 67120d8]
    - [ ] Create a migration adding `semantic_query` (text) and `embedding` (vector, 1536 dims) to `webhook_subscriptions`.
    - [ ] Update the `WebhookSubscription` Eloquent model `$fillable` array.
- [x] Task: Conductor - User Manual Verification 'Phase 1: Database and Model Updates' (Protocol in workflow.md) [commit: c67a16a]

## Phase 2: Background Evaluation Logic [checkpoint: 40dd7b3]
- [x] Task: Implement Webhook Matching [commit: ae75d89]
    - [ ] Update `TriggerWebhooks` listener to evaluate new memories against semantic webhooks using pgvector.
    - [ ] Set a cosine similarity threshold for triggering a match (e.g., > 0.65).
- [x] Task: Write Tests for Semantic Webhooks [commit: ae75d89]
    - [ ] Write a test verifying that a webhook with a semantic query only fires when a relevant memory is stored.
- [x] Task: Conductor - User Manual Verification 'Phase 2: Background Evaluation Logic' (Protocol in workflow.md) [commit: 40dd7b3]

## Phase 3: API and Documentation [checkpoint: 3023e03]
- [x] Task: Update Webhook API [commit: a355cbe]
    - [ ] Update `WebhookController@store` validation to accept `semantic_query` and automatically generate its embedding.
- [x] Task: Update `skill.md` [commit: 8d1cfd0]
    - [ ] Document the new `semantic_query` option for webhooks.
- [x] Task: Conductor - User Manual Verification 'Phase 3: API and Documentation' (Protocol in workflow.md) [commit: 3023e03]