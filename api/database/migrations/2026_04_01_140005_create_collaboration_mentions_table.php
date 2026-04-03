<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('collaboration_mentions', function (Blueprint $table) {
            $table->uuid('id')->primary();
            $table->foreignUuid('workspace_id')->constrained()->cascadeOnDelete();
            $table->foreignUuid('agent_id')->constrained('agents')->cascadeOnDelete(); // sender
            $table->foreignUuid('target_agent_id')->constrained('agents')->cascadeOnDelete(); // receiver
            $table->string('status')->default('pending'); // pending, accepted, declined, completed
            $table->text('message');
            $table->foreignUuid('memory_id')->nullable()->constrained()->cascadeOnDelete();
            $table->foreignUuid('task_id')->nullable()->constrained('workspace_tasks')->cascadeOnDelete();
            $table->text('response')->nullable();
            $table->timestamp('responded_at')->nullable();
            $table->timestamps();

            $table->index(['workspace_id', 'target_agent_id', 'status']);
            $table->index(['workspace_id', 'created_at']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('collaboration_mentions');
    }
};
