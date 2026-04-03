<?php

namespace App\Services;

use App\Models\Agent;
use App\Models\Memory;
use Illuminate\Support\Collection;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;
use RuntimeException;

class SummarizationService
{
    private const GEMINI_MODEL = 'gemini-flash-latest';

    private readonly string $provider;

    private readonly string $geminiKey;

    public function __construct(private readonly BedrockService $bedrock)
    {
        $this->provider = config('app.ai_provider', 'gemini');
        $this->geminiKey = config('services.gemini.key') ?? '';
    }

    /**
     * Compact a collection of memories into a single summary string.
     */
    public function summarize(Collection $memories, Agent $agent): string
    {
        if ($memories->isEmpty()) {
            return '';
        }

        $context = $memories->map(fn ($m) => "- [{$m->key}] {$m->value}")->join("\n");

        $prompt = "You are an AI assistant helping to compact and summarize the memories of an agent named '{$agent->name}'.\n\n";
        $prompt .= "Below are several granular memories. Please synthesize them into a single, high-density, comprehensive summary that retains all the critical facts, insights, and conclusions, but removes redundancy and extreme verbosity.\n\n";
        $prompt .= "Memories to compact:\n".$context."\n\n";
        $prompt .= 'Provide ONLY the final summary text.';

        return $this->callLlm($prompt);
    }

    /**
     * Generate a concise one-sentence summary of a memory value.
     * Returns null for very short values that are already their own summary.
     */
    public function generateSummary(string $value): ?string
    {
        // Short values don't need a summary — they're already concise
        if (mb_strlen($value) < 80) {
            return null;
        }

        $prompt = "Summarize the following text in one concise sentence (max 30 words).\n";
        $prompt .= "Do not add preamble, labels, or quotation marks. Return ONLY the summary sentence.\n\n";
        $prompt .= "Text: {$value}";

        try {
            return $this->callLlm($prompt, 0.1);
        } catch (\Exception $e) {
            Log::warning('Summary generation failed, storing without summary', ['error' => $e->getMessage()]);

            return null;
        }
    }

    /**
     * Extract durable memories from a conversation transcript.
     * Returns an array of memory objects with value, type, key, and importance.
     */
    public function extractMemories(string $transcript, Agent $agent): array
    {
        $validTypes = implode(', ', Memory::TYPES);

        $prompt = "You are an AI assistant analyzing a conversation transcript for an agent named '{$agent->name}'.\n";
        $prompt .= "Extract durable facts, preferences, procedures, and lessons learned from this conversation.\n";
        $prompt .= "Only extract information worth remembering long-term. Skip greetings, small talk, and transient content.\n\n";
        $prompt .= "For each extracted memory, return a JSON array of objects with:\n";
        $prompt .= "- \"value\": the memory content (concise, standalone, max 500 chars)\n";
        $prompt .= "- \"type\": one of [{$validTypes}]\n";
        $prompt .= "- \"key\": a short kebab-case key for deduplication (max 50 chars)\n";
        $prompt .= "- \"importance\": 1-10 rating of how important this is to remember\n\n";
        $prompt .= "Return ONLY a valid JSON array. No preamble, no markdown fences, no explanation.\n";
        $prompt .= "If nothing worth extracting, return an empty array: []\n\n";
        $prompt .= "Transcript:\n{$transcript}";

        $raw = $this->callLlm($prompt, 0.2);

        // Strip any markdown code fences the model might add
        $raw = preg_replace('/^```(?:json)?\s*/i', '', $raw);
        $raw = preg_replace('/\s*```$/', '', $raw);

        $parsed = json_decode(trim($raw), true);
        if (! is_array($parsed)) {
            Log::warning('Session extraction returned invalid JSON', ['raw' => $raw]);

            return [];
        }

        // Validate and sanitize each extracted memory
        $validTypes = Memory::TYPES;

        return array_values(array_filter(array_map(function ($item) use ($validTypes) {
            if (! isset($item['value']) || ! is_string($item['value'])) {
                return null;
            }

            return [
                'value' => mb_substr($item['value'], 0, 500),
                'type' => in_array($item['type'] ?? '', $validTypes) ? $item['type'] : 'note',
                'key' => isset($item['key']) ? mb_substr($item['key'], 0, 50) : null,
                'importance' => max(1, min(10, (int) ($item['importance'] ?? 5))),
            ];
        }, $parsed)));
    }

    /**
     * Route to the configured LLM provider.
     */
    private function callLlm(string $prompt, float $temperature = 0.2): string
    {
        // Try Bedrock first if enabled
        if ($this->bedrock->isEnabled()) {
            $result = $this->bedrock->generateText($prompt);
            if ($result) {
                return $result;
            }
        }

        // Fallback to Gemini
        return $this->callGemini($prompt, $temperature);
    }

    /**
     * Call the Gemini API with a prompt and return the text response.
     */
    public function callGemini(string $prompt, float $temperature = 0.2): string
    {
        $response = Http::post('https://generativelanguage.googleapis.com/v1beta/models/'.self::GEMINI_MODEL.':generateContent?key='.$this->geminiKey, [
            'contents' => [
                ['parts' => [['text' => $prompt]]],
            ],
            'generationConfig' => [
                'temperature' => $temperature,
            ],
        ]);

        if ($response->failed()) {
            throw new RuntimeException('Gemini generation API error: '.$response->body());
        }

        $candidates = $response->json('candidates');
        if (empty($candidates) || ! isset($candidates[0]['content']['parts'][0]['text'])) {
            throw new RuntimeException('Unexpected Gemini response format: '.json_encode($response->json()));
        }

        return trim($candidates[0]['content']['parts'][0]['text']);
    }
}
