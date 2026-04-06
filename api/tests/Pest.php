<?php

use App\Models\Agent;
use App\Models\User;
use Illuminate\Support\Str;
use Tests\TestCase;

/*
|--------------------------------------------------------------------------
| Test Case
|--------------------------------------------------------------------------
|
| The closure you provide to your test functions is always bound to a specific PHPUnit test
| case class. By default, that class is "PHPUnit\Framework\TestCase". Of course, you may
| need to change it using the "pest()" function to bind a different classes or traits.
|
*/

pest()->extend(TestCase::class)
 // ->use(Illuminate\Foundation\Testing\RefreshDatabase::class)
    ->in('Feature');

pest()->extend(TestCase::class)
    ->in('Unit');

/*
|--------------------------------------------------------------------------
| Expectations
|--------------------------------------------------------------------------
|
| When you're writing tests, you often need to check that values meet certain conditions. The
| "expect()" function gives you access to a set of "expectations" methods that you can use
| to assert different things. Of course, you may extend the Expectation API at any time.
|
*/

expect()->extend('toBeOne', function () {
    return $this->toBe(1);
});

/*
|--------------------------------------------------------------------------
| Functions
|--------------------------------------------------------------------------
|
| While Pest is very powerful out-of-the-box, you may have some testing code specific to your
| project that you don't want to repeat in every file. Here you can also expose helpers as
| global functions to help you to reduce the number of lines of code in your test files.
|
*/

function makeOwner(array $overrides = []): User
{
    $token = $overrides['_token'] ?? $overrides['_plaintext_override'] ?? 'owner_'.Str::random(40);
    unset($overrides['_token'], $overrides['_plaintext_override']);
    $user = User::factory()->create(array_merge([
        'api_token_hash' => hash('sha256', $token),
    ], $overrides));
    $user->_plaintext_token = $token;
    return $user;
}

function makeAgent(User $owner, array $overrides = []): Agent
{
    $token = $overrides['_token'] ?? 'amc_'.Str::random(40);
    unset($overrides['_token']);
    $agent = Agent::factory()->create(array_merge([
        'owner_id' => $owner->id,
        'token_hash' => hash('sha256', $token),
    ], $overrides));
    $agent->_plaintext_token = $token;
    return $agent;
}

function withAgent(Agent $agent): array
{
    return ['Authorization' => "Bearer {$agent->_plaintext_token}"];
}
