<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('memories', function (Blueprint $table) {
            $table->unsignedInteger('access_count')->default(0)->after('confidence');
            $table->unsignedInteger('useful_count')->default(0)->after('access_count');
            $table->timestamp('last_accessed_at')->nullable()->after('useful_count');
        });
    }

    public function down(): void
    {
        Schema::table('memories', function (Blueprint $table) {
            $table->dropColumn(['access_count', 'useful_count', 'last_accessed_at']);
        });
    }
};
