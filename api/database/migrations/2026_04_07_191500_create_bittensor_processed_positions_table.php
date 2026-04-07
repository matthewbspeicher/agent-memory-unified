<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     */
    public function up(): void
    {
        if (!Schema::hasTable('bittensor_processed_positions')) {
            Schema::create('bittensor_processed_positions', function (Blueprint $table) {
                $table->string('position_uuid')->primary();
                $table->string('miner_hotkey');
                $table->timestamp('processed_at')->useCurrent();
                $table->timestamps();
            });
        }
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('bittensor_processed_positions');
    }
};
