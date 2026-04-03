<?php

namespace App\Http\Controllers\Auth;

use App\Http\Controllers\Controller;
use App\Models\Agent;
use App\Models\User;
use App\Models\WebhookSubscription;
use App\Services\EmbeddingService;
use App\Services\RequestIdentity;
use Illuminate\Http\Request;
use Illuminate\Support\Str;
use Inertia\Inertia;

class DashboardController extends Controller
{
    public function show(Request $request)
    {
        $user = $request->user();
        $actingAgent = RequestIdentity::agent();

        if ($actingAgent) {
            $actingAgent->loadCount('memories');
            $actingAgent->load('arenaProfile');
            $agents = collect([$actingAgent]);
        } else {
            $agents = $user->agents()->withCount('memories')->with('arenaProfile')->latest()->get();
        }

        $agentCount = $agents->count();
        $avgMemories = $agentCount > 0 ? (int) $agents->avg('memories_count') : 0;

        return Inertia::render('Dashboard', [
            'apiToken' => $user->api_token,
            'actingAgentId' => $actingAgent?->id,
            'agents' => $agents->map(fn ($a) => [
                'id' => $a->id,
                'name' => $a->name,
                'description' => $a->description,
                'created_at' => $a->created_at,
                'arena' => $a->arenaProfile ? [
                    'elo' => $a->arenaProfile->global_elo,
                    'xp' => $a->arenaProfile->xp,
                    'level' => $a->arenaProfile->level,
                ] : null,
            ]),
            'workspaces' => $user->sharedWorkspaces()->select('workspaces.id', 'workspaces.name', 'workspaces.description', 'workspaces.owner_id')->get(),
            'agentCount' => $agentCount,
            'avgMemoriesPerAgent' => $avgMemories,
        ]);
    }

    public function webhooks(Request $request)
    {
        $user = $request->user();
        
        // List webhooks for all agents owned by this user
        $webhooks = WebhookSubscription::whereIn('agent_id', $user->agents()->pluck('id'))
            ->latest()
            ->get();

        return Inertia::render('Webhooks', [
            'webhooks' => $webhooks,
            'availableEvents' => [
                'memory.shared',
                'memory.semantic_match',
                'arena.match_start',
                'trade.opened',
                'trade.closed',
                'position.changed',
                'alert.triggered',
            ],
        ]);
    }

    public function storeWebhook(Request $request)
    {
        $user = $request->user();
        
        $validated = $request->validate([
            'url' => ['required', 'url', 'starts_with:https://'],
            'events' => ['required', 'array', 'min:1'],
            'semantic_query' => ['nullable', 'string', 'max:1000'],
        ]);

        // For simplicity in the UI, we'll attach this to the first agent if none specified
        // In a real multi-agent scenario, we'd have a dropdown.
        $agent = $user->agents()->first();
        
        if (!$agent) {
            return back()->with('error', 'You need to register an agent first.');
        }

        $embedding = null;
        if (in_array('memory.semantic_match', $validated['events']) && ! empty($validated['semantic_query'])) {
            $embeddings = app(EmbeddingService::class);
            $embedding = '['.implode(',', $embeddings->embed($validated['semantic_query'])).']';
        }

        WebhookSubscription::create([
            'agent_id' => $agent->id,
            'url' => $validated['url'],
            'events' => $validated['events'],
            'semantic_query' => $validated['semantic_query'] ?? null,
            'embedding' => $embedding,
            'secret' => 'whsec_'.Str::random(32),
        ]);

        return back()->with('message', 'Webhook registered successfully.');
    }

    public function destroyWebhook(WebhookSubscription $webhook)
    {
        // Ensure user owns the agent attached to the webhook
        if ($webhook->agent->owner_id !== auth()->id()) {
            abort(403);
        }

        $webhook->delete();

        return back()->with('message', 'Webhook deleted.');
    }

    public function testWebhook(WebhookSubscription $webhook)
    {
        if ($webhook->agent->owner_id !== auth()->id()) {
            abort(403);
        }

        \App\Jobs\DispatchWebhook::dispatch($webhook, 'ping', ['message' => 'Manual test ping from dashboard']);

        return back()->with('message', 'Test ping queued.');
    }

    public function registerAgent(Request $request)
    {
        $request->validate([
            'name' => 'required|string|max:255',
            'description' => 'nullable|string|max:1000',
        ]);

        $user = $request->user();

        if ($user->agents()->count() >= $user->maxAgents()) {
            return back()->withErrors(['name' => 'Agent limit reached. Upgrade to Pro for unlimited agents.']);
        }

        $token = Agent::generateToken();

        $request->user()->agents()->create([
            'name' => $request->name,
            'description' => $request->description,
            'api_token' => $token,
            'token_hash' => hash('sha256', $token),
        ]);

        return back()->with('message', "Agent created! Token: {$token}");
    }

    public function destroy(Request $request, Agent $agent)
    {
        if ($request->user()->id !== $agent->owner_id) {
            abort(403);
        }

        $agent->delete();

        return back()->with('message', 'Agent deleted successfully.');
    }

    public function rotateToken(Request $request, Agent $agent)
    {
        if ($request->user()->id !== $agent->owner_id) {
            abort(403);
        }

        $token = Agent::generateToken();

        $agent->update([
            'api_token' => $token,
            'token_hash' => hash('sha256', $token),
        ]);

        return back()->with('message', "Token rotated! New Token: {$token}");
    }

    public function rotateOwnerToken(Request $request)
    {
        $user = $request->user();
        $user->api_token = User::generateToken();
        $user->api_token_hash = hash('sha256', $user->api_token);
        $user->save();

        return back()->with('message', "Owner API token rotated! New Token: {$user->api_token}");
    }
}
