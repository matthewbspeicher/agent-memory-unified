<?php

namespace App\Listeners;

use App\Events\MemoryStored;
use App\Services\AchievementService;
use Illuminate\Contracts\Queue\ShouldQueue;

class AchievementSubscriber implements ShouldQueue
{
    public function __construct(
        private readonly AchievementService $achievements
    ) {}

    public function handleMemoryStored(MemoryStored $event): void
    {
        try {
            $this->achievements->checkAndAward($event->memory->agent, 'store');
        } catch (\Throwable $e) {
            // Achievement check must never break the main operation
        }
    }

    public function subscribe($events): array
    {
        return [
            MemoryStored::class => 'handleMemoryStored',
        ];
    }
}
