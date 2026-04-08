<?php

namespace App\Services;

use App\Contracts\EmbeddingServiceInterface;
use App\Contracts\SummarizationServiceInterface;
use App\Models\Agent;
use App\Models\Memory;
use Illuminate\Pagination\LengthAwarePaginator;

/**
 * @deprecated Use MemoryWriter, MemoryReader, and MemorySharing directly.
 */
class MemoryService
{
    private MemoryWriter $writer;
    private MemoryReader $reader;
    private MemorySharing $sharing;

    public function __construct(
        EmbeddingServiceInterface $embeddings,
        SummarizationServiceInterface $summarizer,
    ) {
        $this->writer = new MemoryWriter($embeddings, $summarizer);
        $this->reader = new MemoryReader();
        $this->sharing = new MemorySharing();
    }

    public function store(Agent $agent, array $data): Memory
    {
        return $this->writer->store($agent, $data);
    }

    public function update(Memory $memory, array $data): Memory
    {
        return $this->writer->update($memory, $data);
    }

    public function delete(Memory $memory): void
    {
        $this->writer->delete($memory);
    }

    public function compact(Agent $agent, array $memoryIds, string $summaryKey): Memory
    {
        return $this->writer->compact($agent, $memoryIds, $summaryKey);
    }

    public function findByKey(Agent $agent, string $key): ?Memory
    {
        return $this->reader->findByKey($agent, $key);
    }

    public function listForAgent(Agent $agent, int $perPage = 20, array $tags = [], ?string $type = null, ?string $category = null): LengthAwarePaginator
    {
        return $this->reader->listForAgent($agent, $perPage, $tags, $type, $category);
    }

    public function shareWith(Memory $memory, Agent $recipient): void
    {
        $this->sharing->shareWith($memory, $recipient);
    }

    public function revokeShare(Memory $memory, Agent $recipient): void
    {
        $this->sharing->revokeShare($memory, $recipient);
    }

    public function recordAccess(Memory $memory): void
    {
        $this->reader->recordAccess($memory);
    }

    public function recordFeedback(Memory $memory, bool $useful): void
    {
        $this->reader->recordFeedback($memory, $useful);
    }
}
