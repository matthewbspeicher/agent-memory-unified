<?php

namespace App\Services;

use Aws\BedrockRuntime\BedrockRuntimeClient;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\Log;

class BedrockService
{
    private ?BedrockRuntimeClient $client = null;
    private bool $enabled;

    public function __construct()
    {
        $this->enabled = config('services.bedrock.enabled', false);

        if ($this->enabled) {
            $this->client = new BedrockRuntimeClient([
                'version' => 'latest',
                'region' => config('services.bedrock.region'),
                'credentials' => [
                    'key' => config('services.bedrock.access_key_id'),
                    'secret' => config('services.bedrock.secret_access_key'),
                ],
            ]);
        }
    }

    public function isEnabled(): bool
    {
        return $this->enabled;
    }

    /**
     * Generate embeddings using Amazon Titan Embeddings
     *
     * @param string $text
     * @return array|null 1024-dimensional vector (Titan v2) or null on failure
     */
    public function embed(string $text): ?array
    {
        if (! $this->enabled || ! $this->client) {
            return null;
        }

        $cacheKey = 'bedrock_embedding_' . hash('sha256', $text);

        return Cache::remember($cacheKey, now()->addDays(30), function () use ($text) {
            try {
                $response = $this->client->invokeModel([
                    'modelId' => config('services.bedrock.embedding_model'),
                    'contentType' => 'application/json',
                    'accept' => 'application/json',
                    'body' => json_encode([
                        'inputText' => $text,
                    ]),
                ]);

                $result = json_decode($response['body'], true);
                return $result['embedding'] ?? null;

            } catch (\Throwable $e) {
                Log::error('Bedrock embedding failed', [
                    'error' => $e->getMessage(),
                    'text_length' => strlen($text),
                ]);
                return null;
            }
        });
    }

    /**
     * Generate text using Claude on Bedrock
     *
     * @param string $prompt
     * @param int $maxTokens
     * @return string|null
     */
    public function generateText(string $prompt, int $maxTokens = 2000): ?string
    {
        if (! $this->enabled || ! $this->client) {
            return null;
        }

        try {
            $response = $this->client->invokeModel([
                'modelId' => config('services.bedrock.text_model'),
                'contentType' => 'application/json',
                'accept' => 'application/json',
                'body' => json_encode([
                    'anthropic_version' => 'bedrock-2023-05-31',
                    'max_tokens' => $maxTokens,
                    'messages' => [
                        [
                            'role' => 'user',
                            'content' => $prompt,
                        ],
                    ],
                ]),
            ]);

            $result = json_decode($response['body'], true);

            if (isset($result['content'][0]['text'])) {
                return $result['content'][0]['text'];
            }

            return null;

        } catch (\Throwable $e) {
            Log::error('Bedrock text generation failed', [
                'error' => $e->getMessage(),
                'prompt_length' => strlen($prompt),
            ]);
            return null;
        }
    }
}
