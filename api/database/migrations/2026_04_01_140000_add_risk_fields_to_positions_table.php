<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('positions', function (Blueprint $table) {
            $table->decimal('declared_portfolio_value', 24, 8)->nullable()->after('avg_entry_price');
            $table->decimal('max_drawdown', 24, 8)->nullable()->after('declared_portfolio_value');
        });
    }

    public function down(): void
    {
        Schema::table('positions', function (Blueprint $table) {
            $table->dropColumn(['declared_portfolio_value', 'max_drawdown']);
        });
    }
};
