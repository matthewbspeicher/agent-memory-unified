<?php

namespace App\Http\Controllers;

use App\Models\User;
use App\Models\Workspace;
use Illuminate\Http\Request;
use Inertia\Inertia;

class WorkspaceSettingsController extends Controller
{
    public function show(Request $request, Workspace $workspace)
    {
        if ($workspace->owner_id !== $request->user()->id) {
            abort(403, 'Only the workspace owner can manage settings.');
        }

        $workspace->load(['users', 'agents']);
        $workspace->makeVisible('api_token');

        return Inertia::render('WorkspaceSettings', [
            'workspace' => $workspace,
        ]);
    }

    public function store(Request $request)
    {
        $validated = $request->validate([
            'name' => ['required', 'string', 'max:255'],
            'description' => ['nullable', 'string', 'max:1000'],
        ]);

        $owner = $request->user();

        if (! $owner->canCreateWorkspace()) {
            return back()->with('error', 'Private workspaces require a Pro subscription.');
        }

        $workspace = Workspace::create([
            'name' => $validated['name'],
            'description' => $validated['description'] ?? null,
            'owner_id' => $owner->id,
        ]);

        $owner->sharedWorkspaces()->attach($workspace->id);

        return back()->with('success', 'Workspace created!');
    }

    public function inviteUser(Request $request, Workspace $workspace)
    {
        if ($workspace->owner_id !== $request->user()->id) {
            abort(403);
        }

        $validated = $request->validate([
            'email' => ['required', 'email'],
        ]);

        $user = User::where('email', $validated['email'])->first();

        if (! $user) {
            return back()->with('error', 'User with that email not found.');
        }

        if ($user->id === $workspace->owner_id) {
            return back()->with('error', 'You cannot invite the owner.');
        }

        $workspace->users()->syncWithoutDetaching([$user->id]);

        return back()->with('success', 'User invited to the workspace.');
    }

    public function removeUser(Request $request, Workspace $workspace, User $user)
    {
        if ($workspace->owner_id !== $request->user()->id) {
            abort(403);
        }

        $workspace->users()->detach($user->id);

        return back()->with('success', 'User removed from the workspace.');
    }

    public function rotateToken(Request $request, Workspace $workspace)
    {
        if ($workspace->owner_id !== $request->user()->id) {
            abort(403);
        }

        $workspace->update(['api_token' => Workspace::generateToken()]);

        return back()->with('success', 'API Token rotated successfully.');
    }
}
