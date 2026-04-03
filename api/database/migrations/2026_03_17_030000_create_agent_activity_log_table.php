<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('agent_activity_log', function (Blueprint $table) {
            $table->id();
            $table->uuid('agent_id');
            $table->string('action', 20);
            $table->timestamp('created_at');
            $table->foreign('agent_id')->references('id')->on('agents')->cascadeOnDelete();
            $table->index(['agent_id', 'created_at']);
            $table->index('created_at');
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('agent_activity_log');
    }
};
