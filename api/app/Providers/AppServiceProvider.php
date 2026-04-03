<?php

namespace App\Providers;

use App\Events\MemoryCreated;
use App\Listeners\ProcessSemanticWebhooks;
use App\Models\Agent;
use App\Models\Trade;
use App\Observers\TradeObserver;
use App\Services\BedrockService;
use App\Services\EmbeddingService;
use Illuminate\Cache\RateLimiting\Limit;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\Event;
use Illuminate\Support\Facades\RateLimiter;
use Illuminate\Support\ServiceProvider;

class AppServiceProvider extends ServiceProvider
{
    /**
     * Register any application services.
     */
    public function register(): void
    {
        $this->app->singleton(BedrockService::class);
        $this->app->singleton(EmbeddingService::class);
    }

    /**
     * Bootstrap any application services.
     */
    public function boot(): void
    {
        // T2: Register correct webhook listener
        Event::listen(
            MemoryCreated::class,
            EvaluateSemanticWebhooks::class,
        );

        // T1: Register trade alert listeners
        Event::listen(\App\Events\TradeClosed::class, [\App\Listeners\EvaluateTradeAlerts::class, 'handleTradeClosed']);
        Event::listen(\App\Events\TradeOpened::class, [\App\Listeners\EvaluateTradeAlerts::class, 'handleTradeOpened']);

        Auth::viaRequest('agent-token', function (Request $request) {
            $token = $request->bearerToken();

            if (! $token || ! str_starts_with($token, 'amc_')) {
                return null;
            }

            return Agent::where('token_hash', hash('sha256', $token))
                ->where('is_active', true)
                ->first();
        });

        RateLimiter::for('api', function (Request $request) {
            if (app()->environment('testing')) {
                return Limit::none();
            }

            return Limit::perMinute(60)->by($request->user()?->id ?: $request->ip());
        });

        RateLimiter::for('agent_api', function (Request $request) {
            if (app()->environment('testing')) {
                return Limit::none();
            }

            $user = $request->user('agent');

            if ($user instanceof Agent) {
                return Limit::perMinute(300)->by($user->id);
            }

            return Limit::perMinute(300)->by($request->ip());
        });

        Trade::observe(TradeObserver::class);
    }
}
