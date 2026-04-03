<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('workspace_subscriptions', function (Blueprint $table) {
            $table->uuid('id')->primary();
            $table->foreignUuid('workspace_id')->constrained()->cascadeOnDelete();
            $table->foreignUuid('agent_id')->constrained()->cascadeOnDelete();
            $table->jsonb('event_types'); // e.g. ["memory.created", "mention.received"]
            $table->string('callback_url')->nullable(); // optional webhook URL
            $table->timestamp('last_polled_at')->nullable();
            $table->timestamps();

            $table->index(['workspace_id', 'agent_id']);
            $table->index('event_types');
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('workspace_subscriptions');
    }
};
