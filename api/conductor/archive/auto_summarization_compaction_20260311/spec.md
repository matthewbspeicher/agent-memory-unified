# Specification: Auto-Summarization & Compaction

## Overview
As agents log highly granular, verbose memories over time, fetching relevant context becomes token-expensive. This track introduces a mechanism to group old, related memories and compress them into a single, high-density summary memory using an LLM, subsequently archiving or deleting the granular components.

## Goals
- Provide an API endpoint for an agent to trigger a "compaction" of a specific memory cluster (by tags, date, or semantic similarity).
- Utilize the Gemini API to summarize the grouped memories.
- Create a new summarized memory and link it to the original memories (via the Knowledge Graph relations) or archive the originals.

## Technical Details
- Setup: Create a `SummarizationService` that takes a collection of `Memory` models, builds a prompt, and calls the Gemini text generation API to summarize them.
- Storage: The resulting summary is stored as a new `Memory` with high `importance`. The original memories have their `visibility` set to `archived` (we will need to add this to the visibility enum).
- API: Create a `POST /api/v1/memories/compact` endpoint.