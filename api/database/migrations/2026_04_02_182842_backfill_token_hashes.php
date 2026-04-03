<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;
use App\Models\Agent;
use App\Models\User;
use App\Models\Workspace;

return new class extends Migration
{
    public function up(): void
    {
        DB::transaction(function () {
            // Backfill agents.token_hash
            Agent::whereNull('token_hash')
                ->whereNotNull('api_token')
                ->chunk(100, function ($agents) {
                    foreach ($agents as $agent) {
                        $agent->updateQuietly(['token_hash' => hash('sha256', $agent->api_token)]);
                    }
                });

            // Backfill users.api_token_hash
            User::whereNull('api_token_hash')
                ->whereNotNull('api_token')
                ->chunk(100, function ($users) {
                    foreach ($users as $user) {
                        $user->updateQuietly(['api_token_hash' => hash('sha256', $user->api_token)]);
                    }
                });

            // Backfill users.magic_link_token_hash
            User::whereNull('magic_link_token_hash')
                ->whereNotNull('magic_link_token')
                ->chunk(100, function ($users) {
                    foreach ($users as $user) {
                        $user->updateQuietly(['magic_link_token_hash' => hash('sha256', $user->magic_link_token)]);
                    }
                });

            // Backfill workspaces.api_token_hash
            Workspace::whereNull('api_token_hash')
                ->whereNotNull('api_token')
                ->chunk(100, function ($workspaces) {
                    foreach ($workspaces as $workspace) {
                        $workspace->updateQuietly(['api_token_hash' => hash('sha256', $workspace->api_token)]);
                    }
                });

            // Assert zero nulls remain
            $agentNulls = Agent::whereNull('token_hash')->whereNotNull('api_token')->count();
            $userApiNulls = User::whereNull('api_token_hash')->whereNotNull('api_token')->count();
            $userMagicLinkNulls = User::whereNull('magic_link_token_hash')->whereNotNull('magic_link_token')->count();
            $workspaceNulls = Workspace::whereNull('api_token_hash')->whereNotNull('api_token')->count();

            if ($agentNulls > 0 || $userApiNulls > 0 || $userMagicLinkNulls > 0 || $workspaceNulls > 0) {
                throw new \Exception("Token hash backfill incomplete: {$agentNulls} agents, {$userApiNulls} users (api_token), {$userMagicLinkNulls} users (magic_link_token), {$workspaceNulls} workspaces still have null hashes");
            }
        });
    }

    public function down(): void
    {
        // No-op: backfilling hashes is non-destructive
    }
};
