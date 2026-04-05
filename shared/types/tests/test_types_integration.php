<?php
/**
 * Integration test: Verify shared types work in Laravel.
 *
 * Run: php test_types_integration.php
 */

require __DIR__ . '/../../../api/vendor/autoload.php';

use AgentMemory\SharedTypes\Agent;

// Test Agent serialization
$agent = new Agent(
    id: '550e8400-e29b-41d4-a716-446655440000',
    name: 'TestAgent',
    owner_id: '660e8400-e29b-41d4-a716-446655440000',
    is_active: true,
    scopes: ['memories:read', 'memories:write'],
    created_at: '2026-04-05T12:00:00Z',
    updated_at: '2026-04-05T12:00:00Z'
);

// Serialize to array
$data = $agent->toArray();
assert($data['name'] === 'TestAgent');
assert($data['is_active'] === true);

// Deserialize from array
$agent2 = Agent::fromArray($data);
assert($agent2->name === $agent->name);
assert($agent2->id === $agent->id);

echo "✅ All PHP integration tests passed\n";
