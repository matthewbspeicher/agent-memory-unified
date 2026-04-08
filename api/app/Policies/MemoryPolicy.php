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
        return $user->workspaces()->where('workspaces.id', $memory->workspace_id)->exists();
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
