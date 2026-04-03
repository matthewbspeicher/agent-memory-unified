<?php

namespace App\Console\Commands;

use App\Models\Agent;
use App\Models\User;
use Illuminate\Console\Command;

class RegisterAgentCommand extends Command
{
    protected $signature = 'app:register-agent
        {name : Agent name}
        {--owner-token= : Owner API token (or pass via OWNER_TOKEN env)}
        {--description= : Short agent description}';

    protected $description = 'Register an agent and display its token';

    public function handle(): int
    {
        $ownerToken = $this->option('owner-token') ?? env('OWNER_TOKEN');

        if (! $ownerToken) {
            $this->error('Provide --owner-token or set OWNER_TOKEN env var.');

            return self::FAILURE;
        }

        $owner = User::where('api_token', $ownerToken)->first();

        if (! $owner) {
            $this->error('Invalid owner token.');

            return self::FAILURE;
        }

        $token = Agent::generateToken();

        $agent = Agent::create([
            'owner_id' => $owner->id,
            'name' => $this->argument('name'),
            'description' => $this->option('description'),
            'api_token' => $token,
        ]);

        $this->info('Agent registered!');
        $this->newLine();
        $this->table(['Field', 'Value'], [
            ['Agent ID', $agent->id],
            ['Name', $agent->name],
            ['Agent Token', $token],
        ]);
        $this->newLine();
        $this->warn('Store this token — it will not be shown again.');

        return self::SUCCESS;
    }
}
