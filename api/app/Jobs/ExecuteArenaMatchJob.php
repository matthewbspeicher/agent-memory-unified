<?php

namespace App\Jobs;

use App\Models\Agent;
use App\Models\ArenaChallenge;
use App\Services\BattleArenaService;
use Illuminate\Bus\Queueable;
use Illuminate\Contracts\Queue\ShouldQueue;
use Illuminate\Foundation\Bus\Dispatchable;
use Illuminate\Queue\InteractsWithQueue;
use Illuminate\Queue\SerializesModels;

class ExecuteArenaMatchJob implements ShouldQueue
{
    use Dispatchable, InteractsWithQueue, Queueable, SerializesModels;

    public function __construct(
        public readonly Agent $p1,
        public readonly Agent $p2,
        public readonly ArenaChallenge $challenge
    ) {}

    public function handle(BattleArenaService $arenaService): void
    {
        $arenaService->executeMatch($this->p1, $this->p2, $this->challenge);
    }
}
