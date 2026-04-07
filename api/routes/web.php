<?php

use App\Http\Controllers\Auth\DashboardController;
use App\Http\Controllers\Auth\MagicLinkController;
use App\Http\Controllers\WorkspaceSettingsController;
use Illuminate\Support\Facades\Route;

Route::get('/health', fn () => response('ok', 200));

Route::get('/docs', function () {
    return view('docs');
});

// -------------------------------------------------------------------------
// Authentication
// -------------------------------------------------------------------------

Route::post('/login', [MagicLinkController::class, 'sendLink'])->name('login');

// -------------------------------------------------------------------------
// Dashboard routes (authenticated via session)
// -------------------------------------------------------------------------

Route::middleware(['auth'])->group(function () {
    Route::get('/dashboard', [DashboardController::class, 'show'])->name('dashboard');

    Route::delete('/dashboard/agents/{agent}', [DashboardController::class, 'destroy'])->name('dashboard.agents.destroy');
    Route::post('/dashboard/agents/{agent}/rotate', [DashboardController::class, 'rotateToken'])->name('dashboard.agents.rotate');
    Route::post('/dashboard/token/rotate', [DashboardController::class, 'rotateOwnerToken'])->name('dashboard.token.rotate');
});

