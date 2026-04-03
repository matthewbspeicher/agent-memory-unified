<?php

use Illuminate\Foundation\Inspiring;
use Illuminate\Support\Facades\Artisan;
use Illuminate\Support\Facades\Schedule;

Artisan::command('inspire', function () {
    $this->comment(Inspiring::quote());
})->purpose('Display an inspiring quote');

Schedule::command('memories:prune')->hourly();
Schedule::command('memories:auto-compact')->hourly();
Schedule::command('app:prune-activity-log')->daily();

// Launch Bots
Schedule::command('bot:hackernews')->hourlyAt(15);
Schedule::command('bot:promptengineer')->twiceDaily(9, 15);
Schedule::command('bot:systemobserver')->dailyAt('23:00');
Schedule::command('bot:newsletter')->weeklyOn(5, '09:00');
