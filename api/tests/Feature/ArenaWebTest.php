<?php

namespace Tests\Feature;

use Tests\TestCase;

class ArenaWebTest extends TestCase
{
    public function test_arena_page_renders(): void
    {
        $response = $this->get('/arena');

        $response->assertOk();
    }
}
