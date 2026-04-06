<?php

namespace App\Console\Commands;

use App\Models\InviteCode;
use Illuminate\Console\Command;

class GenerateInviteCode extends Command
{
    protected $signature = 'invite:generate
        {--label= : Label for this invite (e.g. "for mike")}
        {--max-uses=1 : How many times this code can be used}
        {--expires= : Expiration date (e.g. "2026-05-01")}
        {--count=1 : Number of codes to generate}';

    protected $description = 'Generate invite codes for new user registration';

    public function handle(): int
    {
        $count = (int) $this->option('count');
        $label = $this->option('label');
        $maxUses = (int) $this->option('max-uses');
        $expires = $this->option('expires')
            ? new \DateTimeImmutable($this->option('expires'))
            : null;

        $codes = [];
        for ($i = 0; $i < $count; $i++) {
            [$invite, $plainCode] = InviteCode::generate(
                label: $label,
                maxUses: $maxUses,
                expiresAt: $expires,
            );
            $codes[] = $plainCode;
        }

        $this->info("Generated {$count} invite code(s):");
        foreach ($codes as $code) {
            $this->line("  {$code}");
        }

        if ($expires) {
            $this->comment("Expires: {$expires->format('Y-m-d')}");
        }
        if ($maxUses > 1) {
            $this->comment("Max uses per code: {$maxUses}");
        }

        return self::SUCCESS;
    }
}
