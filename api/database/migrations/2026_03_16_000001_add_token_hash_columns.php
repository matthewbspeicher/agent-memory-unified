<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('users', function (Blueprint $table) {
            $table->string('api_token_hash')->nullable()->index()->after('api_token');
            $table->string('magic_link_token_hash')->nullable()->index()->after('magic_link_token');
        });

        Schema::table('agents', function (Blueprint $table) {
            $table->string('token_hash')->nullable()->index()->after('api_token');
        });

        Schema::table('workspaces', function (Blueprint $table) {
            $table->string('api_token_hash')->nullable()->index()->after('api_token');
        });

        // Make plaintext token columns nullable (Stage 1.2 preparation)
        Schema::table('agents', function (Blueprint $table) {
            $table->string('api_token', 80)->nullable()->change();
        });

        Schema::table('users', function (Blueprint $table) {
            $table->string('api_token', 80)->nullable()->change();
        });

        Schema::table('workspaces', function (Blueprint $table) {
            $table->string('api_token', 80)->nullable()->change();
        });

        // Backfill existing tokens
        DB::table('agents')->whereNotNull('api_token')->orderBy('id')->chunk(100, function ($agents) {
            foreach ($agents as $agent) {
                DB::table('agents')->where('id', $agent->id)->update([
                    'token_hash' => hash('sha256', $agent->api_token),
                ]);
            }
        });

        DB::table('users')->whereNotNull('api_token')->orderBy('id')->chunk(100, function ($users) {
            foreach ($users as $user) {
                $updates = ['api_token_hash' => hash('sha256', $user->api_token)];
                if ($user->magic_link_token) {
                    $updates['magic_link_token_hash'] = hash('sha256', $user->magic_link_token);
                }
                DB::table('users')->where('id', $user->id)->update($updates);
            }
        });

        DB::table('workspaces')->whereNotNull('api_token')->orderBy('id')->chunk(100, function ($workspaces) {
            foreach ($workspaces as $workspace) {
                DB::table('workspaces')->where('id', $workspace->id)->update([
                    'api_token_hash' => hash('sha256', $workspace->api_token),
                ]);
            }
        });
    }

    public function down(): void
    {
        Schema::table('users', function (Blueprint $table) {
            $table->dropColumn(['api_token_hash', 'magic_link_token_hash']);
        });

        Schema::table('agents', function (Blueprint $table) {
            $table->dropColumn('token_hash');
        });

        Schema::table('workspaces', function (Blueprint $table) {
            $table->dropColumn('api_token_hash');
        });
    }
};
