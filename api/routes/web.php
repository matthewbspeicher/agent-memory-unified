<?php

use App\Http\Controllers\Auth\DashboardController;
use App\Http\Controllers\Auth\MagicLinkController;
use App\Http\Controllers\WorkspaceSettingsController;
use Illuminate\Support\Facades\Route;

Route::get('/health', fn () => response('ok', 200));

Route::get('/skill.md', fn () => response()->file(public_path('skill.md'), ['Content-Type' => 'text/markdown']));

Route::get('/docs', function () {
    return view('docs');
});

// Auth — magic link flow
Route::middleware('guest')->group(function () {
    Route::get('/login', [MagicLinkController::class, 'showLogin'])->name('login');
    Route::post('/login', [MagicLinkController::class, 'sendLink'])->middleware('throttle:3,1');
    Route::get('/auth/check-email', [MagicLinkController::class, 'checkEmail'])->name('auth.check-email');
});

Route::get('/auth/verify/{token}', [MagicLinkController::class, 'verifyLink'])->name('auth.verify');

// Authenticated
Route::middleware('auth')->group(function () {
    Route::get('/dashboard', [DashboardController::class, 'show'])->name('dashboard');
    Route::post('/dashboard/token/rotate', [DashboardController::class, 'rotateOwnerToken'])->name('dashboard.token.rotate');
    Route::post('/dashboard/agents', [DashboardController::class, 'registerAgent'])->name('dashboard.register-agent');
    Route::delete('/dashboard/agents/{agent}', [DashboardController::class, 'destroy'])->name('dashboard.agents.destroy');
    Route::post('/dashboard/agents/{agent}/rotate', [DashboardController::class, 'rotateToken'])->name('dashboard.agents.rotate');
    Route::post('/logout', [MagicLinkController::class, 'logout'])->name('logout');

    // Webhooks
    Route::get('/dashboard/webhooks', [DashboardController::class, 'webhooks'])->name('dashboard.webhooks');
    Route::post('/dashboard/webhooks', [DashboardController::class, 'storeWebhook'])->name('dashboard.webhooks.store');
    Route::delete('/dashboard/webhooks/{webhook}', [DashboardController::class, 'destroyWebhook'])->name('dashboard.webhooks.destroy');
    Route::post('/dashboard/webhooks/{webhook}/test', [DashboardController::class, 'testWebhook'])->name('dashboard.webhooks.test');

    // Workspace Settings
    Route::post('/workspaces', [WorkspaceSettingsController::class, 'store'])->name('workspaces.store');
    Route::get('/workspaces/{workspace}/settings', [WorkspaceSettingsController::class, 'show'])->name('workspaces.settings');
    Route::post('/workspaces/{workspace}/invite', [WorkspaceSettingsController::class, 'inviteUser'])->name('workspaces.invite');
    Route::delete('/workspaces/{workspace}/users/{user}', [WorkspaceSettingsController::class, 'removeUser'])->name('workspaces.remove-user');
    Route::post('/workspaces/{workspace}/token/rotate', [WorkspaceSettingsController::class, 'rotateToken'])->name('workspaces.token.rotate');
});
