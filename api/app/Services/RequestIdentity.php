<?php

namespace App\Services;

use App\Models\Agent;
use App\Models\User;
use Illuminate\Support\Facades\Auth;

class RequestIdentity
{
    /**
     * Get the currently authenticated agent, if any.
     */
    public static function agent(): ?Agent
    {
        $agent = Auth::guard('agent')->user();
        
        return $agent instanceof Agent ? $agent : null;
    }

    /**
     * Get the currently acting user (owner).
     */
    public static function user(): ?User
    {
        return Auth::guard('web')->user();
    }

    /**
     * Is the current request authenticated as an agent?
     */
    public static function isAgent(): bool
    {
        return self::agent() !== null;
    }

    /**
     * Is the current request authenticated as a human user?
     */
    public static function isHuman(): bool
    {
        return self::user() !== null && ! self::isAgent();
    }
}
