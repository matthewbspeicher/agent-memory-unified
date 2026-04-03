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
        Schema::create('arena_tournaments', function (Blueprint $table) {
            $table->id();
            $table->string('name');
            $table->string('type')->default('daily'); // daily, weekly, grand
            $table->string('status')->default('scheduled'); // scheduled, open, in_progress, completed
            $table->json('rewards')->nullable();
            $table->timestamp('starts_at')->nullable();
            $table->timestamp('ends_at')->nullable();
            $table->timestamps();
        });

        Schema::create('arena_tournament_participants', function (Blueprint $table) {
            $table->id();
            $table->foreignId('tournament_id')->constrained('arena_tournaments')->cascadeOnDelete();
            $table->foreignUuid('agent_id')->constrained('agents')->cascadeOnDelete();
            $table->integer('rank')->nullable();
            $table->integer('score')->default(0);
            $table->string('status')->default('active'); // active, eliminated, winner
            $table->timestamps();
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('arena_tournament_participants');
        Schema::dropIfExists('arena_tournaments');
    }
};
