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
        Schema::create('arena_session_turns', function (Blueprint $table) {
            $table->id();
            $table->foreignId('session_id')->constrained('arena_sessions')->cascadeOnDelete();
            $table->integer('turn_number');
            $table->json('agent_payload');
            $table->json('validator_response')->nullable();
            $table->timestamps();
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('arena_session_turns');
    }
};
