<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;

class AgentActivityLog extends Model
{
    public $timestamps = false;

    protected $table = 'agent_activity_log';

    protected $fillable = ['agent_id', 'action', 'created_at'];

    protected $casts = ['created_at' => 'datetime'];
}
