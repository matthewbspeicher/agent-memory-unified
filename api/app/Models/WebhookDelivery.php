<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;

class WebhookDelivery extends Model
{
    protected $fillable = [
        'subscription_id',
        'event',
        'payload',
        'response_status',
        'attempt',
    ];

    protected $casts = [
        'payload' => 'array',
    ];

    public function subscription()
    {
        return $this->belongsTo(WebhookSubscription::class);
    }
}
