<?php

namespace Tests\Feature;

use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class ArenaWebTest extends TestCase
{
    use RefreshDatabase;

    public function test_arena_api_gyms_endpoint_renders(): void
    {
        $agent = makeAgent(makeOwner());

        $response = $this->getJson('/api/v1/arena/gyms', withAgent($agent));

        $response->assertOk();
    }
}
