<?php

namespace App\Http\Middleware;

use App\Services\RequestIdentity;
use Illuminate\Http\Request;
use Inertia\Middleware;

class HandleInertiaRequests extends Middleware
{
    protected $rootView = 'app';

    public function share(Request $request): array
    {
        return array_merge(parent::share($request), [
            'auth' => [
                'user' => $request->user(),
                'agent' => RequestIdentity::isAgent() ? [
                    'id' => RequestIdentity::agent()->id,
                    'name' => RequestIdentity::agent()->name,
                ] : null,
            ],
            'flash' => [
                'message' => fn () => $request->session()->get('message'),
            ],
        ]);
    }
}
