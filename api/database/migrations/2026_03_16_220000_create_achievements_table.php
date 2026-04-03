<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('achievements', function (Blueprint $table) {
            $table->id();
            $table->uuid('agent_id');
            $table->string('achievement_slug', 50);
            $table->timestamp('earned_at');
            $table->foreign('agent_id')->references('id')->on('agents')->cascadeOnDelete();
            $table->unique(['agent_id', 'achievement_slug']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('achievements');
    }
};
