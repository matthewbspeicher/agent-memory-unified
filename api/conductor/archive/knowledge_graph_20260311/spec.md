# Specification: The Knowledge Graph

## Overview
This track introduces relational linking between memories, transforming the flat memory store into a traversable Knowledge Graph. Agents will be able to link new memories to existing ones (e.g., as a child, continuation, or related thought), enabling context traversal.

## Goals
- Allow memories to define relational links to other memories.
- Update the API to support creating these links during memory creation or update.
- Update the API to retrieve a memory's relations (parents/children or general links).

## Technical Details
- Database: Create a `memory_relations` pivot table to support many-to-many relationships between memories (since a memory might be related to multiple other memories), or add a `parent_id` column. We will use a `memory_relations` pivot table to support flexible graph structures (source_id, target_id, relation_type).
- Models: Update `Memory` model with `relations` or `relatedMemories` relationships.
- API: Add support for passing `relations: ["uuid1", "uuid2"]` in the store/update endpoints. Optionally support fetching graph context.