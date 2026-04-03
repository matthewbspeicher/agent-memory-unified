<?php

use App\Models\Agent;
use App\Models\Memory;
use Database\Seeders\CommonsSeeder;
use Illuminate\Foundation\Testing\RefreshDatabase;

uses(RefreshDatabase::class);

it('creates the Remembr system agent', function () {
    $this->seed(CommonsSeeder::class);

    $agent = Agent::where('name', 'Remembr')->first();
    expect($agent)->not->toBeNull();
    expect($agent->description)->toBe('Curated developer knowledge');
});

it('creates typed public memories', function () {
    $this->seed(CommonsSeeder::class);

    $agent = Agent::where('name', 'Remembr')->first();
    $memories = Memory::where('agent_id', $agent->id)->get();

    expect($memories)->toHaveCount(40);
    expect($memories->where('visibility', 'public'))->toHaveCount(40);

    // Verify type distribution
    expect($memories->where('type', 'error_fix')->count())->toBe(10);
    expect($memories->where('type', 'tool_tip')->count())->toBe(10);
    expect($memories->where('type', 'procedure')->count())->toBe(8);
    expect($memories->where('type', 'fact')->count())->toBe(7);
    expect($memories->where('type', 'lesson')->count())->toBe(5);
});

it('is idempotent', function () {
    $this->seed(CommonsSeeder::class);
    $this->seed(CommonsSeeder::class);

    expect(Agent::where('name', 'Remembr')->count())->toBe(1);
    expect(Memory::where('agent_id', Agent::where('name', 'Remembr')->first()->id)->count())->toBe(40);
});
