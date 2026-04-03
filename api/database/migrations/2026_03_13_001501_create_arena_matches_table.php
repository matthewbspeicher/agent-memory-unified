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
        Schema::create('arena_matches', function (Blueprint $table) {
            $table->id();
            $table->foreignUuid('agent_1_id')->constrained('agents')->cascadeOnDelete();
            $table->foreignUuid('agent_2_id')->constrained('agents')->cascadeOnDelete();
            $table->foreignId('challenge_id')->nullable()->constrained('arena_challenges')->nullOnDelete(); // The drafted challenge
            $table->foreignUuid('winner_id')->nullable()->constrained('agents')->nullOnDelete();
            $table->string('status')->default('drafting'); // drafting, in_progress, completed, cancelled
            $table->timestamps();
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('arena_matches');
    }
};
