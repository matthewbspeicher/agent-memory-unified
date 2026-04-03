<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Models\Memory;
use Illuminate\Http\Request;
use Symfony\Component\HttpFoundation\StreamedResponse;

class CommonsStreamController extends Controller
{
    public function __invoke(Request $request): StreamedResponse
    {
        $request->validate([
            'tags' => 'nullable|array',
            'tags.*' => 'string',
        ]);

        return response()->stream(function () use ($request) {
            // Disable all output buffering so SSE events flush immediately
            while (ob_get_level() > 0) {
                ob_end_clean();
            }

            $tags = $request->query('tags');

            $applyTags = function ($query) use ($tags) {
                $query->when(! empty($tags), function ($q) use ($tags) {
                    foreach ($tags as $tag) {
                        $q->whereJsonContains('metadata->tags', $tag);
                    }
                });
            };

            $totalMemories = Memory::where('visibility', 'public')->tap($applyTags)->count();

            $this->sendEvent('connected', [
                'message' => 'Listening for public memories…',
                'total_memories' => $totalMemories,
            ]);

            $lastChecked = now();
            $pollsSinceStats = 0;

            while (true) {
                if (connection_aborted()) {
                    break;
                }

                $memories = Memory::query()
                    ->where('visibility', 'public')
                    ->where('created_at', '>', $lastChecked)
                    ->with('agent:id,name,description')
                    ->orderBy('created_at')
                    ->limit(50)
                    ->tap($applyTags)
                    ->get();

                if ($memories->isNotEmpty()) {
                    $lastChecked = $memories->last()->created_at;
                    $totalMemories += $memories->count();

                    foreach ($memories as $memory) {
                        $this->sendEvent('memory.created', [
                            'id' => $memory->id,
                            'key' => $memory->key,
                            'value' => $memory->value,
                            'visibility' => $memory->visibility,
                            'metadata' => $memory->metadata,
                            'created_at' => $memory->created_at->toIso8601String(),
                            'agent' => [
                                'id' => $memory->agent->id,
                                'name' => $memory->agent->name,
                                'description' => $memory->agent->description,
                            ],
                        ]);
                    }
                }

                // Send stats every ~30 seconds (15 polls × 2s)
                $pollsSinceStats++;
                if ($pollsSinceStats >= 15) {
                    $totalMemories = Memory::where('visibility', 'public')->tap($applyTags)->count();

                    $this->sendEvent('stats', [
                        'total_memories' => $totalMemories,
                    ]);
                    $pollsSinceStats = 0;
                }

                echo ": heartbeat\n\n";
                flush();

                sleep(2);
            }
        }, 200, [
            'Content-Type' => 'text/event-stream',
            'Cache-Control' => 'no-cache',
            'Connection' => 'keep-alive',
            'X-Accel-Buffering' => 'no',
        ]);
    }

    private function sendEvent(string $event, array $data): void
    {
        echo "event: {$event}\n";
        echo 'data: '.json_encode($data)."\n\n";
        flush();
    }
}
