<?php

namespace App\Contracts;

interface EmbeddingServiceInterface
{
    /**
     * Generate an embedding vector for the given text.
     */
    public function embed(string $text): array;

    /**
     * Embed multiple texts in a single API call (more efficient).
     */
    public function embedBatch(array $texts): array;
}
