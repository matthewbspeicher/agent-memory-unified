<?php

namespace App\Traits;

use AgentMemory\SharedEvents\EventPublisher;
use Illuminate\Support\Facades\Redis;

trait IsEventable
{
    public static function bootIsEventable()
    {
        static::created(function ($model) {
            $model->publishEvent('created');
            if (method_exists($model, 'onCreatedEvent')) {
                $model->onCreatedEvent();
            }
        });

        static::updated(function ($model) {
            $model->publishEvent('updated');
            if (method_exists($model, 'onUpdatedEvent')) {
                $model->onUpdatedEvent();
            }
        });

        static::deleted(function ($model) {
            $model->publishEvent('deleted');
            if (method_exists($model, 'onDeletedEvent')) {
                $model->onDeletedEvent();
            }
        });
    }

    protected function publishEvent(string $action)
    {
        $publisher = new EventPublisher(
            Redis::connection()->client(),
            'events'
        );

        if (method_exists($this, 'getCustomEventName')) {
            $eventName = $this->getCustomEventName($action);
            if (!$eventName) {
                return; // Skip publishing if explicitly null
            }
        } else {
            $eventName = class_basename(static::class) . ucfirst($action);
        }

        $payload = method_exists($this, 'getCustomEventPayload') 
            ? $this->getCustomEventPayload($action) 
            : $this->getEventPayload();

        $publisher->publish($eventName, $payload);
    }

    protected function getEventPayload(): array
    {
        return $this->toArray();
    }
}
