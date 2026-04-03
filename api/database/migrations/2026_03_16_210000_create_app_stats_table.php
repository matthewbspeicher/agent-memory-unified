<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('app_stats', function (Blueprint $table) {
            $table->string('key', 100)->primary();
            $table->bigInteger('value')->default(0);
            $table->timestamp('updated_at')->nullable();
        });

        DB::table('app_stats')->insert([
            ['key' => 'searches_performed', 'value' => 0, 'updated_at' => now()],
        ]);
    }

    public function down(): void
    {
        Schema::dropIfExists('app_stats');
    }
};
