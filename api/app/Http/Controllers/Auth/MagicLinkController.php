<?php

namespace App\Http\Controllers\Auth;

use App\Http\Controllers\Controller;
use App\Mail\MagicLinkMail;
use App\Models\User;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\Mail;
use Illuminate\Support\Str;
use Inertia\Inertia;

class MagicLinkController extends Controller
{
    public function showLogin()
    {
        return Inertia::render('Auth/Login');
    }

    public function sendLink(Request $request)
    {
        $request->validate([
            'name' => 'required|string|max:255',
            'email' => 'required|email|max:255',
        ]);

        $apiToken = 'own_'.Str::random(40);
        $user = User::firstOrCreate(
            ['email' => $request->email],
            [
                'name' => $request->name,
                'password' => bcrypt(Str::random(32)),
                'api_token' => $apiToken,
                'api_token_hash' => hash('sha256', $apiToken),
            ],
        );

        $token = $user->generateMagicLink();

        $url = url("/auth/verify/{$token}");

        Mail::to($user->email)->send(new MagicLinkMail($url));

        return redirect()->route('auth.check-email')->with('email', $user->email);
    }

    public function checkEmail(Request $request)
    {
        return Inertia::render('Auth/CheckEmail', [
            'email' => session('email'),
        ]);
    }

    public function verifyLink(string $token)
    {
        $tokenHash = hash('sha256', $token);
        $user = User::where('magic_link_token_hash', $tokenHash)
            ->orWhere('magic_link_token', $token)
            ->first();

        if (! $user || ! $user->hasValidMagicLink($token)) {
            return redirect()->route('login')->with('message', 'This link is invalid or has expired. Please request a new one.');
        }

        $user->clearMagicLink();
        $user->ensureApiToken();

        Auth::login($user, remember: true);

        return redirect()->route('dashboard');
    }

    public function logout(Request $request)
    {
        Auth::logout();
        $request->session()->invalidate();
        $request->session()->regenerateToken();

        return redirect()->route('login');
    }
}
