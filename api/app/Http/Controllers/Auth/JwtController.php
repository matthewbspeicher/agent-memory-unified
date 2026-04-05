<?php

namespace App\Http\Controllers\Auth;

use App\Http\Controllers\Controller;
use Illuminate\Http\Request;
use Shared\Auth\JWTValidator;
use Illuminate\Support\Facades\Redis;

class JwtController extends Controller
{
    private JWTValidator $validator;

    public function __construct()
    {
        $this->validator = new JWTValidator(
            Redis::connection()->client(),
            config('auth.jwt_secret'),
            config('auth.jwt_algorithm', 'HS256')
        );
    }

    /**
     * Issue a new JWT for the authenticated agent.
     *
     * POST /api/v1/auth/jwt
     */
    public function issue(Request $request)
    {
        $agent = auth('agent')->user();

        if (!$agent) {
            return response()->json(['error' => 'Unauthorized'], 401);
        }

        $expiryMinutes = config('auth.jwt_expiry_minutes', 15);

        $token = $this->validator->issue(
            subject: $agent->id,
            type: 'agent',
            scopes: $agent->scopes ?? [],
            expiryMinutes: $expiryMinutes
        );

        return response()->json([
            'token' => $token,
            'token_type' => 'Bearer',
            'expires_in' => $expiryMinutes * 60,  // seconds
        ]);
    }

    /**
     * Refresh an existing JWT.
     *
     * POST /api/v1/auth/refresh
     */
    public function refresh(Request $request)
    {
        // Same logic as issue - validates current token, issues new one
        return $this->issue($request);
    }
}
