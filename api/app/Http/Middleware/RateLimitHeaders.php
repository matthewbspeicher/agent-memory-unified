<?php

namespace App\Http\Middleware;

use Closure;
use Illuminate\Http\Request;
use Symfony\Component\HttpFoundation\Response;

class RateLimitHeaders
{
    public function handle(Request $request, Closure $next): Response
    {
        $response = $next($request);

        // Laravel's throttle middleware sets these on the response already.
        // We just ensure they're always present with clean names.
        if ($response->headers->has('X-RateLimit-Limit')) {
            $response->headers->set('X-RateLimit-Reset',
                $response->headers->get('Retry-After')
                    ? (string) (time() + (int) $response->headers->get('Retry-After'))
                    : (string) (time() + 60)
            );
        }

        return $response;
    }
}
