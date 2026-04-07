<?php

namespace App\Http\Controllers\Api;

use App\Contracts\EmbeddingServiceInterface;

use App\Http\Controllers\Controller;
use App\Jobs\DispatchWebhook;
use App\Models\WebhookSubscription;
use App\Traits\ResolvesAgent;
use App\Http\Requests\CreateWebhookRequest;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Str;

class WebhookController extends Controller
{
    use ResolvesAgent;

    public function index(Request $request): JsonResponse
    {
        $agent = $this->resolveAgent($request);
        if ($agent instanceof JsonResponse) {
            return $agent;
        }
        $webhooks = WebhookSubscription::where('agent_id', $agent->id)->get();

        return response()->json(['data' => $webhooks]);
    }

    public function store(CreateWebhookRequest $request): JsonResponse
    {
        $agent = $this->resolveAgent($request);
        if ($agent instanceof JsonResponse) {
            return $agent;
        }

        if (WebhookSubscription::where('agent_id', $agent->id)->count() >= 5) {
            return response()->json(['error' => 'Webhook limit reached. Maximum 5 webhooks per agent.'], 422);
        }

        $validated = $request->validated();

        if (in_array('memory.semantic_match', $validated['events']) && empty($validated['semantic_query'])) {
            return response()->json([
                'message' => 'The semantic query field is required when events contains memory.semantic_match.',
                'errors' => ['semantic_query' => ['The semantic query field is required when events contains memory.semantic_match.']],
            ], 422);
        }

        $embedding = null;
        if (in_array('memory.semantic_match', $validated['events']) && ! empty($validated['semantic_query'])) {
            $embeddings = app(\App\Contracts\EmbeddingServiceInterface::class);
            $embedding = '['.implode(',', $embeddings->embed($validated['semantic_query'])).']';
        }

        $webhook = WebhookSubscription::create([
            'agent_id' => $agent->id,
            'url' => $validated['url'],
            'events' => $validated['events'],
            'semantic_query' => $validated['semantic_query'] ?? null,
            'embedding' => $embedding,
            'secret' => 'whsec_'.Str::random(32),
        ]);

        return response()->json($webhook->makeVisible('secret'), 201);
    }

    public function destroy(Request $request, string $id): JsonResponse
    {
        $agent = $this->resolveAgent($request);
        if ($agent instanceof JsonResponse) {
            return $agent;
        }
        $webhook = WebhookSubscription::where('agent_id', $agent->id)->where('id', $id)->first();

        if (! $webhook) {
            return response()->json(['error' => 'Webhook not found.'], 404);
        }

        $webhook->delete();

        return response()->json(['message' => 'Webhook deleted.']);
    }

    public function test(Request $request, string $id): JsonResponse
    {
        $agent = $this->resolveAgent($request);
        if ($agent instanceof JsonResponse) {
            return $agent;
        }
        $webhook = WebhookSubscription::where('agent_id', $agent->id)->where('id', $id)->first();

        if (! $webhook) {
            return response()->json(['error' => 'Webhook not found.'], 404);
        }

        DispatchWebhook::dispatch($webhook, 'ping', ['message' => 'Webhook test ping']);

        return response()->json(['message' => 'Test ping queued.']);
    }
}
