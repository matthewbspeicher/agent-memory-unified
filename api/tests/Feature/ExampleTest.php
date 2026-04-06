<?php

namespace Tests\Feature;

use Tests\TestCase;

class ExampleTest extends TestCase
{
    /**
     * A basic test to ensure the application responds.
     */
    public function test_the_application_returns_a_successful_response(): void
    {
        $response = $this->get('/health');

        $response->assertStatus(200);
    }
}
