<?php

declare(strict_types=1);

namespace App\Events;

use App\Models\Agent;
use Illuminate\Foundation\Events\Dispatchable;
use Illuminate\Queue\SerializesModels;

final class AchievementUnlocked
{
    use Dispatchable, SerializesModels;

    /**
     * Create a new event instance.
     *
     * @param  Agent  $agent  The agent who unlocked the achievement
     * @param  string  $slug  The achievement slug being unlocked
     * @param  array  $context  Additional context about the trigger
     */
    public function __construct(
        public Agent $agent,
        public string $slug,
        public array $context = [],
    ) {
    }
}