<?php

use App\Models\Agent;
use App\Models\Memory;
use App\Services\EmbeddingService;
use App\Services\SummarizationService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Carbon;

uses(RefreshDatabase::class);

// Mock embeddings for all tests — we don't want real OpenAI calls
beforeEach(function () {
    $this->mock(EmbeddingService::class, function ($mock) {
        $mock->shouldReceive('embed')
            ->andReturn(array_fill(0, 1536, 0.1));

        $mock->shouldReceive('embedBatch')
            ->andReturn([array_fill(0, 1536, 0.1)]);
    });
});

// ---------------------------------------------------------------------------
// Memory — Compact
// ---------------------------------------------------------------------------

describe('POST /v1/memories/compact', function () {
    it('compacts multiple memories into one and archives the originals', function () {
        $agent = makeAgent(makeOwner());

        $mem1 = Memory::factory()->create(['agent_id' => $agent->id, 'key' => 'm1', 'value' => 'Fact 1']);
        $mem2 = Memory::factory()->create(['agent_id' => $agent->id, 'key' => 'm2', 'value' => 'Fact 2']);

        $this->mock(SummarizationService::class, function ($mock) {
            $mock->shouldReceive('summarize')->once()->andReturn('Combined Fact 1 and 2');
            $mock->shouldReceive('generateSummary')->andReturn(null);
        });

        $response = $this->postJson('/api/v1/memories/compact', [
            'keys' => ['m1', 'm2'],
            'summary_key' => 'm_summary',
        ], withAgent($agent));

        $response->assertCreated()
            ->assertJsonFragment([
                'key' => 'm_summary',
                'value' => 'Combined Fact 1 and 2',
            ]);

        $this->assertDatabaseHas('memories', [
            'agent_id' => $agent->id,
            'key' => 'm1',
            'visibility' => 'archived',
        ]);

        $this->assertDatabaseHas('memories', [
            'agent_id' => $agent->id,
            'key' => 'm2',
            'visibility' => 'archived',
        ]);

        // Check relations were created
        $summaryId = $response->json('id');
        $this->assertDatabaseHas('memory_relations', [
            'source_id' => $summaryId,
            'target_id' => $mem1->id,
            'type' => 'compacted_from',
        ]);
    });
});

// ---------------------------------------------------------------------------
// Agent Registration
// ---------------------------------------------------------------------------

describe('POST /v1/agents/register', function () {

    it('registers an agent with a valid owner token', function () {
        $owner = makeOwner();

        $response = $this->postJson('/api/v1/agents/register', [
            'name' => 'TestBot',
            'description' => 'A test agent',
            'owner_token' => $owner->api_token,
        ]);

        $response->assertCreated()
            ->assertJsonStructure(['agent_id', 'agent_token', 'message'])
            ->assertJsonFragment(['message' => 'Agent registered. Store your agent_token — it will not be shown again.']);

        expect($response->json('agent_token'))->toStartWith('amc_');
    });

    it('rejects registration with an invalid owner token', function () {
        $response = $this->postJson('/api/v1/agents/register', [
            'name' => 'TestBot',
            'owner_token' => 'bad_token',
        ]);

        $response->assertUnauthorized();
    });

    it('requires a name', function () {
        makeOwner();

        $response = $this->postJson('/api/v1/agents/register', [
            'owner_token' => 'owner_test_token',
        ]);

        $response->assertUnprocessable()
            ->assertJsonValidationErrors(['name']);
    });

});

// ---------------------------------------------------------------------------
// Memory — Type in Response
// ---------------------------------------------------------------------------

describe('Memory type in response', function () {
    it('includes type in memory response', function () {
        $agent = makeAgent(makeOwner());
        $memory = Memory::factory()->create([
            'agent_id' => $agent->id,
            'key' => 'type-test',
            'value' => 'test value',
            'type' => 'fact',
            'visibility' => 'private',
        ]);

        $response = $this->getJson('/api/v1/memories/type-test', withAgent($agent));

        $response->assertOk();
        $response->assertJsonPath('type', 'fact');
    });
});

// ---------------------------------------------------------------------------
// Memory — Store
// ---------------------------------------------------------------------------

describe('POST /v1/memories', function () {

    it('stores a private memory with default importance and confidence', function () {
        $agent = makeAgent(makeOwner());

        $response = $this->postJson('/api/v1/memories', [
            'key' => 'user-preference',
            'value' => 'The user prefers dark mode.',
            'visibility' => 'private',
        ], withAgent($agent));

        $response->assertCreated()
            ->assertJsonFragment([
                'key' => 'user-preference',
                'value' => 'The user prefers dark mode.',
                'visibility' => 'private',
                'importance' => 5,
                'confidence' => 1.0,
            ]);

        expect(Memory::where('agent_id', $agent->id)->count())->toBe(1);
    });

    it('stores a memory with custom importance and confidence', function () {
        $agent = makeAgent(makeOwner());

        $response = $this->postJson('/api/v1/memories', [
            'key' => 'allergy-info',
            'value' => 'The user is severely allergic to peanuts.',
            'importance' => 10,
            'confidence' => 0.95,
        ], withAgent($agent));

        $response->assertCreated()
            ->assertJsonFragment([
                'importance' => 10,
                'confidence' => 0.95,
            ]);

        $this->assertDatabaseHas('memories', [
            'agent_id' => $agent->id,
            'key' => 'allergy-info',
            'importance' => 10,
            'confidence' => 0.95,
        ]);
    });

    it('stores a memory with relations', function () {
        $agent = makeAgent(makeOwner());
        $parentMemory = Memory::factory()->create(['agent_id' => $agent->id]);

        $response = $this->postJson('/api/v1/memories', [
            'key' => 'child-thought',
            'value' => 'A thought derived from the parent.',
            'relations' => [
                [
                    'id' => $parentMemory->id,
                    'type' => 'parent',
                ],
            ],
        ], withAgent($agent));

        $response->assertCreated();

        $responseData = $response->json();
        expect($responseData['relations'])->toHaveCount(1);
        expect($responseData['relations'][0]['id'])->toBe($parentMemory->id);
        expect($responseData['relations'][0]['type'])->toBe('parent');

        $this->assertDatabaseHas('memory_relations', [
            'target_id' => $parentMemory->id,
            'type' => 'parent',
        ]);
    });

    it('stores a public memory', function () {
        $agent = makeAgent(makeOwner());

        $response = $this->postJson('/api/v1/memories', [
            'value' => 'The sky is blue.',
            'visibility' => 'public',
        ], withAgent($agent));

        $response->assertCreated()
            ->assertJsonFragment(['visibility' => 'public']);
    });

    it('upserts when key already exists', function () {
        $agent = makeAgent(makeOwner());

        $this->postJson('/api/v1/memories', [
            'key' => 'my-key',
            'value' => 'original value',
        ], withAgent($agent));

        $this->postJson('/api/v1/memories', [
            'key' => 'my-key',
            'value' => 'updated value',
        ], withAgent($agent));

        expect(Memory::where('agent_id', $agent->id)->count())->toBe(1);
        expect(Memory::where('agent_id', $agent->id)->first()->value)->toBe('updated value');
    });

    it('accepts valid memory type on store', function () {
        $agent = makeAgent(makeOwner());
        $response = $this->postJson('/api/v1/memories', [
            'value' => 'PostgreSQL IVFFlat needs >100 rows',
            'type' => 'error_fix',
        ], withAgent($agent));
        $response->assertCreated();
        $response->assertJsonPath('type', 'error_fix');
    });

    it('rejects invalid memory type on store', function () {
        $agent = makeAgent(makeOwner());
        $response = $this->postJson('/api/v1/memories', [
            'value' => 'some value',
            'type' => 'invalid_type',
        ], withAgent($agent));
        $response->assertUnprocessable();
        $response->assertJsonValidationErrors('type');
    });

    it('defaults to note type when not specified', function () {
        $agent = makeAgent(makeOwner());
        $response = $this->postJson('/api/v1/memories', [
            'value' => 'no type specified',
        ], withAgent($agent));
        $response->assertCreated();
        $response->assertJsonPath('type', 'note');
    });

    it('rejects unauthenticated requests', function () {
        $this->postJson('/api/v1/memories', [
            'value' => 'some value',
        ])->assertUnauthorized();
    });

    it('requires a value', function () {
        $agent = makeAgent(makeOwner());

        $this->postJson('/api/v1/memories', [], withAgent($agent))
            ->assertUnprocessable()
            ->assertJsonValidationErrors(['value']);
    });

    it('stores metadata', function () {
        $agent = makeAgent(makeOwner());

        $response = $this->postJson('/api/v1/memories', [
            'value' => 'remembered something',
            'metadata' => ['custom' => 'value'],
            'tags' => ['important', 'user'],
        ], withAgent($agent));

        $response->assertCreated()
            ->assertJsonFragment(['tags' => ['important', 'user']])
            ->assertJsonFragment(['metadata' => ['custom' => 'value']]);

        // Check DB directly
        $memory = Memory::first();
        expect($memory->metadata['tags'])->toBe(['important', 'user']);
    });

    it('sets expires_at from ttl shorthand', function () {
        $agent = makeAgent(makeOwner());

        $response = $this->postJson('/api/v1/memories', [
            'value' => 'temporary memory',
            'ttl' => '24h',
        ], withAgent($agent));

        $response->assertCreated();
        $expiresAt = Carbon::parse($response->json('expires_at'));

        // Assert it expires in approximately 24 hours (allow a few seconds variance)
        expect($expiresAt->diffInMinutes(now()->addHours(24)))->toBeLessThan(2);
    });

    it('rejects request with both ttl and expires_at', function () {
        $agent = makeAgent(makeOwner());

        $this->postJson('/api/v1/memories', [
            'value' => 'temporary memory',
            'ttl' => '24h',
            'expires_at' => now()->addDays(2)->toIso8601String(),
        ], withAgent($agent))
            ->assertUnprocessable()
            ->assertJsonValidationErrors(['ttl', 'expires_at']);
    });

    it('rejects too many tags', function () {
        $agent = makeAgent(makeOwner());

        $this->postJson('/api/v1/memories', [
            'value' => 'too many tags',
            'tags' => array_fill(0, 11, 'tag'),
        ], withAgent($agent))
            ->assertUnprocessable()
            ->assertJsonValidationErrors(['tags']);
    });

    it('rejects invalid ttl format', function () {
        $agent = makeAgent(makeOwner());

        $this->postJson('/api/v1/memories', [
            'value' => 'temporary memory',
            'ttl' => 'invalid',
        ], withAgent($agent))
            ->assertUnprocessable()
            ->assertJsonValidationErrors(['ttl']);
    });

});

// ---------------------------------------------------------------------------
// Memory — Retrieve
// ---------------------------------------------------------------------------

describe('GET /v1/memories/{key}', function () {

    it('retrieves a memory by key', function () {
        $agent = makeAgent(makeOwner());

        Memory::factory()->create([
            'agent_id' => $agent->id,
            'key' => 'my-key',
            'value' => 'my value',
        ]);

        $this->getJson('/api/v1/memories/my-key', withAgent($agent))
            ->assertOk()
            ->assertJsonFragment(['key' => 'my-key', 'value' => 'my value']);
    });

    it('returns 404 for unknown key', function () {
        $agent = makeAgent(makeOwner());

        $this->getJson('/api/v1/memories/nonexistent', withAgent($agent))
            ->assertNotFound();
    });

    it('cannot retrieve another agent\'s private memory', function () {
        $owner = makeOwner();
        $agentA = makeAgent($owner, ['api_token' => 'amc_agent_a']);
        $agentB = makeAgent($owner, ['api_token' => 'amc_agent_b']);

        Memory::factory()->create([
            'agent_id' => $agentA->id,
            'key' => 'secret',
            'value' => 'secret value',
            'visibility' => 'private',
        ]);

        $this->getJson('/api/v1/memories/secret', withAgent($agentB))
            ->assertNotFound();
    });

    it('does not return expired memories', function () {
        $agent = makeAgent(makeOwner());

        Memory::factory()->create([
            'agent_id' => $agent->id,
            'key' => 'expired-key',
            'expires_at' => now()->subDay(),
        ]);

        $this->getJson('/api/v1/memories/expired-key', withAgent($agent))
            ->assertNotFound();
    });

});

// ---------------------------------------------------------------------------
// Memory — Update
// ---------------------------------------------------------------------------

describe('PATCH /v1/memories/{key}', function () {

    it('updates a memory value', function () {
        $agent = makeAgent(makeOwner());

        Memory::factory()->create([
            'agent_id' => $agent->id,
            'key' => 'updatable',
            'value' => 'old value',
        ]);

        $this->patchJson('/api/v1/memories/updatable', [
            'value' => 'new value',
        ], withAgent($agent))
            ->assertOk()
            ->assertJsonFragment(['value' => 'new value']);
    });

    it('updates memory relations', function () {
        $agent = makeAgent(makeOwner());

        $parent = Memory::factory()->create(['agent_id' => $agent->id]);
        $child = Memory::factory()->create([
            'agent_id' => $agent->id,
            'key' => 'child-key',
        ]);

        $this->patchJson('/api/v1/memories/child-key', [
            'relations' => [
                [
                    'id' => $parent->id,
                    'type' => 'related',
                ],
            ],
        ], withAgent($agent))
            ->assertOk();

        $this->assertDatabaseHas('memory_relations', [
            'source_id' => $child->id,
            'target_id' => $parent->id,
            'type' => 'related',
        ]);
    });

    it('allows type to be updated', function () {
        $agent = makeAgent(makeOwner());
        $this->postJson('/api/v1/memories', [
            'key' => 'update-type-test',
            'value' => 'original value',
            'type' => 'note',
        ], withAgent($agent));
        $response = $this->patchJson('/api/v1/memories/update-type-test', [
            'type' => 'lesson',
        ], withAgent($agent));
        $response->assertOk();
        $response->assertJsonPath('type', 'lesson');
    });

    it('updates visibility', function () {
        $agent = makeAgent(makeOwner());

        Memory::factory()->create([
            'agent_id' => $agent->id,
            'key' => 'private-key',
            'visibility' => 'private',
        ]);

        $this->patchJson('/api/v1/memories/private-key', [
            'visibility' => 'public',
        ], withAgent($agent))
            ->assertOk()
            ->assertJsonFragment(['visibility' => 'public']);
    });

});

// ---------------------------------------------------------------------------
// Memory — Delete
// ---------------------------------------------------------------------------

describe('DELETE /v1/memories/{key}', function () {

    it('deletes a memory', function () {
        $agent = makeAgent(makeOwner());

        Memory::factory()->create([
            'agent_id' => $agent->id,
            'key' => 'deletable',
        ]);

        $this->deleteJson('/api/v1/memories/deletable', [], withAgent($agent))
            ->assertOk()
            ->assertJsonFragment(['message' => 'Memory deleted.']);

        expect(Memory::where('agent_id', $agent->id)->count())->toBe(0);
    });

});

// ---------------------------------------------------------------------------
// Memory — Type Filtering
// ---------------------------------------------------------------------------

describe('Type filtering', function () {
    it('filters memories by type in list endpoint', function () {
        $agent = makeAgent(makeOwner());
        Memory::factory()->create(['agent_id' => $agent->id, 'key' => 'fact-mem', 'value' => 'a fact', 'type' => 'fact']);
        Memory::factory()->create(['agent_id' => $agent->id, 'key' => 'lesson-mem', 'value' => 'a lesson', 'type' => 'lesson']);
        $response = $this->getJson('/api/v1/memories?type=fact', withAgent($agent));
        $response->assertOk();
        $response->assertJsonCount(1, 'data');
        $response->assertJsonPath('data.0.type', 'fact');
    });

    it('filters memories by type in search endpoint', function () {
        $agent = makeAgent(makeOwner());
        Memory::factory()->create(['agent_id' => $agent->id, 'value' => 'PostgreSQL error fix for booleans', 'type' => 'error_fix']);
        Memory::factory()->create(['agent_id' => $agent->id, 'value' => 'PostgreSQL is a great database', 'type' => 'fact']);
        $response = $this->getJson('/api/v1/memories/search?q=postgresql&type=error_fix', withAgent($agent));
        $response->assertOk();
        collect($response->json('data'))->each(fn ($m) => expect($m['type'])->toBe('error_fix'));
    });
});

// ---------------------------------------------------------------------------
// Memory — Semantic Search
// ---------------------------------------------------------------------------

describe('GET /v1/memories/search', function () {

    it('returns search results for the agent', function () {
        $agent = makeAgent(makeOwner());

        Memory::factory(3)->create(['agent_id' => $agent->id]);

        $this->getJson('/api/v1/memories/search?q=test+query', withAgent($agent))
            ->assertOk()
            ->assertJsonStructure(['data' => [['id', 'key', 'value', 'similarity']]]);
    });

    it('filters search results by tags', function () {
        $agent = makeAgent(makeOwner());

        Memory::factory()->create(['agent_id' => $agent->id, 'value' => 'test a', 'metadata' => ['tags' => ['foo']]]);
        Memory::factory()->create(['agent_id' => $agent->id, 'value' => 'test b', 'metadata' => ['tags' => ['bar']]]);

        $response = $this->getJson('/api/v1/memories/search?q=test&tags=foo', withAgent($agent));

        $response->assertOk();
        expect(count($response->json('data')))->toBe(1);
        expect($response->json('data.0.value'))->toBe('test a');
    });

    it('requires a query parameter', function () {
        $agent = makeAgent(makeOwner());

        $this->getJson('/api/v1/memories/search', withAgent($agent))
            ->assertUnprocessable()
            ->assertJsonValidationErrors(['q']);
    });

});

// ---------------------------------------------------------------------------
// Commons Search
// ---------------------------------------------------------------------------

describe('GET /v1/commons/search', function () {

    it('returns public memories from all agents', function () {
        $owner = makeOwner();
        $agentA = makeAgent($owner, ['api_token' => 'amc_agent_a']);
        $agentB = makeAgent($owner, ['api_token' => 'amc_agent_b']);

        Memory::factory()->create([
            'agent_id' => $agentB->id,
            'visibility' => 'public',
            'value' => 'public knowledge',
        ]);

        Memory::factory()->create([
            'agent_id' => $agentB->id,
            'visibility' => 'private',
            'value' => 'private knowledge',
        ]);

        $response = $this->getJson('/api/v1/commons/search?q=knowledge', withAgent($agentA));

        $response->assertOk();

        $values = collect($response->json('data'))->pluck('value');
        expect($values)->toContain('public knowledge')
            ->not->toContain('private knowledge');
    });

    it('filters commons search results by type', function () {
        $owner = makeOwner();
        $agentA = makeAgent($owner, ['api_token' => 'amc_agent_a']);
        $agentB = makeAgent($owner, ['api_token' => 'amc_agent_b']);

        Memory::factory()->create([
            'agent_id' => $agentB->id,
            'visibility' => 'public',
            'value' => 'PostgreSQL error fix for booleans',
            'type' => 'error_fix',
        ]);

        Memory::factory()->create([
            'agent_id' => $agentB->id,
            'visibility' => 'public',
            'value' => 'PostgreSQL is a great database',
            'type' => 'fact',
        ]);

        $response = $this->getJson('/api/v1/commons/search?q=postgresql&type=error_fix', withAgent($agentA));

        $response->assertOk();
        collect($response->json('data'))->each(fn ($m) => expect($m['type'])->toBe('error_fix'));
    });

});

// ---------------------------------------------------------------------------
// Sharing
// ---------------------------------------------------------------------------

describe('POST /v1/memories/{key}/share', function () {

    it('shares a memory with another agent', function () {
        $owner = makeOwner();
        $agentA = makeAgent($owner, ['api_token' => 'amc_agent_a']);
        $agentB = makeAgent($owner, ['api_token' => 'amc_agent_b']);

        Memory::factory()->create([
            'agent_id' => $agentA->id,
            'key' => 'shared-key',
            'value' => 'shared value',
        ]);

        $this->postJson('/api/v1/memories/shared-key/share', [
            'agent_id' => $agentB->id,
        ], withAgent($agentA))
            ->assertOk();
    });

    it('rejects sharing a non-existent memory', function () {
        $owner = makeOwner();
        $agentA = makeAgent($owner, ['api_token' => 'amc_agent_a']);
        $agentB = makeAgent($owner, ['api_token' => 'amc_agent_b']);

        $this->postJson('/api/v1/memories/nonexistent/share', [
            'agent_id' => $agentB->id,
        ], withAgent($agentA))
            ->assertNotFound();
    });

});
