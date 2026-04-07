<?php

namespace App\Contracts;

use App\Models\Agent;
use Illuminate\Support\Collection;

interface SummarizationServiceInterface
{
    /**
     * Compact a collection of memories into a single summary string.
     */
    public function summarize(Collection $memories, Agent $agent): string;

    /**
     * Generate a concise one-sentence summary of a memory value.
     */
    public function generateSummary(string $value): ?string;

    /**
     * Extract durable memories from a conversation transcript.
     */
    public function extractMemories(string $transcript, Agent $agent): array;
}
