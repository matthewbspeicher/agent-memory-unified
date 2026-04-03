<?php

use App\Http\Middleware\AuthenticateAgent;
use App\Http\Middleware\HandleInertiaRequests;
use App\Http\Middleware\RateLimitHeaders;
use Illuminate\Foundation\Application;
use Illuminate\Foundation\Configuration\Exceptions;
use Illuminate\Foundation\Configuration\Middleware;

return Application::configure(basePath: dirname(__DIR__))
    ->withRouting(
        web: __DIR__.'/../routes/web.php',
        api: __DIR__.'/../routes/api.php',
        commands: __DIR__.'/../routes/console.php',
        health: '/up',
    )
    ->withMiddleware(function (Middleware $middleware): void {
        $middleware->web(
            prepend: [
                AuthenticateAgent::class,
            ],
            append: [
                HandleInertiaRequests::class,
            ]
        );
        $middleware->alias([
            'agent.auth' => AuthenticateAgent::class,
            'agent.scope' => \App\Http\Middleware\EnforceAgentScopes::class,
            'rate.headers' => RateLimitHeaders::class,
        ]);
        $middleware->validateCsrfTokens(except: ['stripe/*']);
    })
    ->withExceptions(function (Exceptions $exceptions): void {
        //
    })->create();
