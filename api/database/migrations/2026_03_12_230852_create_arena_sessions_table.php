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
        Schema::create('arena_sessions', function (Blueprint $table) {
            $table->id();
            $table->foreignUuid('agent_id')->constrained('agents')->cascadeOnDelete();
            $table->foreignId('challenge_id')->constrained('arena_challenges')->cascadeOnDelete();
            $table->string('status')->default('in_progress'); // in_progress, completed, failed
            $table->integer('score')->nullable();
            $table->timestamp('ended_at')->nullable();
            $table->timestamps(); // automatically provides started_at conceptually via created_at
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('arena_sessions');
    }
};
