<?php

namespace Tests\Feature;

use App\Http\Controllers\Api\MemoryController;
use App\Models\Agent;
use App\Models\Memory;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Http\Request;
use Tests\TestCase;

class CommonsPaginationTest extends TestCase
{
    use RefreshDatabase;

    public function test_can_paginate_commons()
    {
        $this->withoutExceptionHandling();
        $user = User::factory()->create();
        $agent = Agent::factory()->create(['owner_id' => $user->id]);

        // Create 15 public memories
        for ($i = 0; $i < 15; $i++) {
            Memory::factory()->create([
                'agent_id' => $agent->id,
                'visibility' => 'public',
                'created_at' => now()->subMinutes($i), // Ensure predictable ordering
            ]);
        }

        // Also create some private memories to ensure they don't leak
        Memory::factory()->count(5)->create([
            'agent_id' => $agent->id,
            'visibility' => 'private',
        ]);

        $response = $this->withHeaders([
            'Authorization' => "Bearer {$agent->api_token}",
        ])->getJson('/api/v1/commons?limit=10');

        $response->assertStatus(200)
            ->assertJsonCount(10, 'data')
            ->assertJsonPath('data.0.visibility', 'public')
            ->assertJsonStructure([
                'data' => [
                    '*' => [
                        'id', 'key', 'value', 'type', 'visibility',
                        'agent' => ['id', 'name', 'description'],
                    ],
                ],
                'meta' => ['next_cursor', 'prev_cursor', 'per_page', 'has_more'],
            ]);

        $this->assertTrue($response->json('meta.has_more'));
        $nextCursor = $response->json('meta.next_cursor');

        $response2 = $this->withHeaders([
            'Authorization' => "Bearer {$agent->api_token}",
        ])->getJson("/api/v1/commons?limit=10&cursor={$nextCursor}");

        $response2->assertStatus(200)
            ->assertJsonCount(5, 'data');

        $this->assertFalse($response2->json('meta.has_more'));
    }

    public function test_can_filter_commons_by_type()
    {
        $user = User::factory()->create();
        $agent = Agent::factory()->create(['owner_id' => $user->id]);

        Memory::factory()->create(['agent_id' => $agent->id, 'visibility' => 'public', 'type' => 'prompt']);
        Memory::factory()->create(['agent_id' => $agent->id, 'visibility' => 'public', 'type' => 'prompt']);
        Memory::factory()->create(['agent_id' => $agent->id, 'visibility' => 'public', 'type' => 'note']);

        $request = Request::create('/api/v1/commons', 'GET', ['type' => 'prompt']);
        $request->attributes->set('agent', $agent);
        $response = app(MemoryController::class)->commonsIndex($request);

        $this->assertEquals(200, $response->getStatusCode());
        $data = $response->getData(true);
        $this->assertCount(2, $data['data']);

        foreach ($data['data'] as $item) {
            $this->assertEquals('prompt', $item['type']);
        }
    }

    public function test_can_filter_commons_by_tags()
    {
        $user = User::factory()->create();
        $agent = Agent::factory()->create(['owner_id' => $user->id]);

        Memory::factory()->create(['agent_id' => $agent->id, 'visibility' => 'public', 'metadata' => ['tags' => ['ai', 'future']]]);
        Memory::factory()->create(['agent_id' => $agent->id, 'visibility' => 'public', 'metadata' => ['tags' => ['ai']]]);
        Memory::factory()->create(['agent_id' => $agent->id, 'visibility' => 'public', 'metadata' => ['tags' => ['programming']]]);

        $request = Request::create('/api/v1/commons', 'GET', ['tags' => 'ai']);
        $request->attributes->set('agent', $agent);
        $response = app(MemoryController::class)->commonsIndex($request);

        $this->assertEquals(200, $response->getStatusCode());
        $data = $response->getData(true);
        $this->assertCount(2, $data['data']);
    }
}
