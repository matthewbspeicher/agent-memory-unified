<?php

namespace App\Policies;

use App\Models\User;
use App\Models\Agent;
use App\Models\Memory;

class MemoryPolicy
{
    /**
     * Determine whether the user can view the model.
     */
    public function view(User|Agent $user, Memory $memory): bool
    {
        // If memory is not part of a workspace, it's private to the agent.
        if (!$memory->workspace_id) {
            return $user instanceof Agent && $memory->agent_id === $user->id;
        }

        // If it is in a workspace, the agent must be part of that workspace
        if ($user instanceof Agent) {
            return $user->workspaces()->where('workspaces.id', $memory->workspace_id)->exists();
        }

        // We only authorize Agents for memory API right now, Users are not used
        return false;
    }

    /**
     * Determine whether the user can update the model.
     */
    public function update(User|Agent $user, Memory $memory): bool
    {
        return $this->view($user, $memory);
    }

    /**
     * Determine whether the user can delete the model.
     */
    public function delete(User|Agent $user, Memory $memory): bool
    {
        return $this->view($user, $memory);
    }
}
