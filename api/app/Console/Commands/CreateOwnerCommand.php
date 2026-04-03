<?php

namespace App\Console\Commands;

use App\Models\User;
use Illuminate\Console\Command;
use Illuminate\Support\Str;

class CreateOwnerCommand extends Command
{
    protected $signature = 'app:create-owner
        {email : Owner email address}
        {--name= : Owner name (defaults to email local part)}';

    protected $description = 'Create an owner account and display the API token';

    public function handle(): int
    {
        $email = $this->argument('email');

        if (User::where('email', $email)->exists()) {
            $this->error("User with email {$email} already exists.");

            return self::FAILURE;
        }

        $token = 'own_'.Str::random(40);

        $user = User::create([
            'name' => $this->option('name') ?? Str::before($email, '@'),
            'email' => $email,
            'password' => bcrypt(Str::random(32)),
            'api_token' => $token,
        ]);

        $this->info('Owner created!');
        $this->newLine();
        $this->table(['Field', 'Value'], [
            ['Email', $user->email],
            ['Name', $user->name],
            ['Owner Token', $token],
        ]);
        $this->newLine();
        $this->warn('Store this token — it will not be shown again.');

        return self::SUCCESS;
    }
}
