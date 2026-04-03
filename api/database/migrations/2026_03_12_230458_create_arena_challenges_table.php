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
        Schema::create('arena_challenges', function (Blueprint $table) {
            $table->id();
            $table->foreignId('gym_id')->constrained('arena_gyms')->cascadeOnDelete();
            $table->string('title');
            $table->text('prompt');
            $table->integer('difficulty_level')->default(1);
            $table->integer('xp_reward')->default(10);
            $table->string('validator_type'); // e.g., 'built_in_regex', 'external_webhook', 'llm_judge'
            $table->json('validator_config')->nullable();
            $table->timestamps();
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('arena_challenges');
    }
};
