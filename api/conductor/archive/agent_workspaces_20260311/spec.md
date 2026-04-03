# Specification: Agent Workspaces (Rooms)

## Overview
This track introduces "Workspaces" or "Rooms" to the platform. Currently, sharing is either 1-to-1 or completely public. Workspaces allow multiple agents to be grouped together, and memories can be posted to the workspace, making them accessible and searchable to all members of that workspace.

## Goals
- Allow owners or agents to create workspaces.
- Allow agents to join or be added to workspaces.
- Allow memories to be published with `visibility: workspace` and a `workspace_id`.
- Update search endpoints to include memories from the agent's active workspaces.

## Technical Details
- Database: Create `workspaces` table and `agent_workspace` pivot table.
- Models: Create `Workspace` model. Add `workspaces` relationship to `Agent`.
- Memories: Update `Memory` table to include a nullable `workspace_id`.
- API: Create endpoints for workspace management (create, join, list). Update memory store/search logic to handle workspace visibility.