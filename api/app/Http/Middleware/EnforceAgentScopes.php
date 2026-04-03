<?php

namespace App\Http\Middleware;

use Closure;
use Illuminate\Http\Request;
use Symfony\Component\HttpFoundation\Response;

class EnforceAgentScopes
{
    /**
     * Handle an incoming request.
     */
    public function handle(Request $request, Closure $next, string $scope): Response
    {
        $agent = $request->attributes->get('agent');

        if (! $agent) {
            return response()->json(['error' => 'Authentication required.'], 401);
        }

        if (! $agent->hasScope($scope)) {
            return response()->json([
                'error' => "Insufficient permissions. This agent lacks the '{$scope}' scope.",
            ], 403);
        }

        // Also protect sensitive owner routes from any agent-authenticated request
        // even if they don't have a specific scope check.
        if ($agent && $this->isSensitiveRoute($request)) {
            return response()->json([
                'error' => 'This action is restricted to human owners only.',
            ], 403);
        }

        return $next($request);
    }

    private function isSensitiveRoute(Request $request): bool
    {
        $sensitivePatterns = [
            '#dashboard/agents/\w+/rotate#',
            '#dashboard/token/rotate#',
            '#workspaces/\w+/invite#',
            '#workspaces/\w+/users/\w+#',
        ];

        foreach ($sensitivePatterns as $pattern) {
            if (preg_match($pattern, $request->path())) {
                return true;
            }
        }

        return false;
    }
}
