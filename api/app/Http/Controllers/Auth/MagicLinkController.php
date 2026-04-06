<?php

namespace App\Http\Controllers\Auth;

use App\Http\Controllers\Controller;
use App\Mail\MagicLinkMail;
use App\Models\InviteCode;
use App\Models\User;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\Mail;
use Illuminate\Support\Str;

class MagicLinkController extends Controller
{
    public function showLogin()
    {
        return response()->json(['message' => 'Use POST /login with name and email to request a magic link.']);
    }

    public function sendLink(Request $request)
    {
        $request->validate([
            'name' => 'required|string|max:255',
            'email' => 'required|email|max:255',
            'invite_code' => 'nullable|string|max:255',
        ]);

        // Existing users can log in without an invite code
        $existingUser = User::where('email', $request->email)->first();

        if (! $existingUser) {
            // New users require a valid invite code
            if (! $request->invite_code) {
                return back()->withErrors(['invite_code' => 'An invite code is required to create a new account.']);
            }

            $invite = InviteCode::findByCode($request->invite_code);
            if (! $invite || ! $invite->isValid()) {
                return back()->withErrors(['invite_code' => 'Invalid or expired invite code.']);
            }
        }

        $apiToken = 'own_'.Str::random(40);
        $user = User::firstOrCreate(
            ['email' => $request->email],
            [
                'name' => $request->name,
                'password' => bcrypt(Str::random(32)),
                'api_token_hash' => hash('sha256', $apiToken),
            ],
        );

        // Redeem the invite if this was a new user creation
        if (! $existingUser && isset($invite)) {
            $invite->redeem($user);
        }

        $token = $user->generateMagicLink();

        $url = url("/auth/verify/{$token}");

        Mail::to($user->email)->send(new MagicLinkMail($url));

        return redirect()->route('auth.check-email')->with('email', $user->email);
    }

    public function checkEmail(Request $request)
    {
        return response()->json([
            'message' => 'Check your email for the magic link.',
            'email' => session('email'),
        ]);
    }

    public function verifyLink(string $token)
    {
        $tokenHash = hash('sha256', $token);
        $user = User::where('magic_link_token_hash', $tokenHash)
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
