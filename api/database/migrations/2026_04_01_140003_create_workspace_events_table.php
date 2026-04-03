<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('workspace_events', function (Blueprint $table) {
            $table->uuid('id')->primary();
            $table->foreignUuid('workspace_id')->constrained()->cascadeOnDelete();
            $table->string('event_type'); // e.g. "memory.created", "presence.updated"
            $table->foreignUuid('actor_agent_id')->nullable()->constrained('agents')->nullOnDelete();
            $table->json('payload'); // event-specific data
            $table->timestamps();

            $table->index(['workspace_id', 'created_at']);
            $table->index('event_type');
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('workspace_events');
    }
};
