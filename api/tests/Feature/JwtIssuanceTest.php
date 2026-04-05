<?php

namespace Tests\Feature;

use Tests\TestCase;
use App\Models\Agent;
use Illuminate\Foundation\Testing\RefreshDatabase;

class JwtIssuanceTest extends TestCase
{
    use RefreshDatabase;

    public function test_issues_jwt_for_agent()
    {
        $agent = Agent::factory()->create([
            'token_hash' => hash('sha256', 'amc_test_token'),
            'is_active' => true,
            'scopes' => ['memories:write', 'trading:execute'],
        ]);

        $response = $this->withHeaders([
            'Authorization' => 'Bearer amc_test_token',
        ])->postJson('/api/v1/auth/jwt');

        $response->assertStatus(200);
        $response->assertJsonStructure([
            'token',
            'expires_in',
            'token_type',
        ]);

        $this->assertEquals('Bearer', $response->json('token_type'));
        $this->assertEquals(900, $response->json('expires_in'));

        // Verify JWT can be decoded
        $token = $response->json('token');
        $this->assertNotEmpty($token);
        $this->assertStringNotContainsString('amc_', $token);  // Should be JWT, not legacy
    }

    public function test_requires_authentication()
    {
        $response = $this->postJson('/api/v1/auth/jwt');

        $response->assertStatus(401);
    }

    public function test_jwt_contains_correct_claims()
    {
        $agent = Agent::factory()->create([
            'token_hash' => hash('sha256', 'amc_test'),
            'scopes' => ['memories:write'],
        ]);

        $response = $this->withHeaders([
            'Authorization' => 'Bearer amc_test',
        ])->postJson('/api/v1/auth/jwt');

        $token = $response->json('token');

        // Decode without verification for inspection
        $parts = explode('.', $token);
        $payload = json_decode(base64_decode($parts[1]), true);

        $this->assertEquals($agent->id, $payload['sub']);
        $this->assertEquals('agent', $payload['type']);
        $this->assertContains('memories:write', $payload['scopes']);
        $this->assertArrayHasKey('exp', $payload);
        $this->assertArrayHasKey('iat', $payload);
    }
}
