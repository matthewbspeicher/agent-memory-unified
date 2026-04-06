<?php

use App\Http\Controllers\Auth\DashboardController;
use App\Http\Controllers\Auth\MagicLinkController;
use App\Http\Controllers\WorkspaceSettingsController;
use Illuminate\Support\Facades\Route;

Route::get('/health', fn () => response('ok', 200));

Route::get('/docs', function () {
    return view('docs');
});

