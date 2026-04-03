<?php

use App\Http\Controllers\Api\AchievementController;
use App\Http\Controllers\Api\AgentController;
use App\Http\Controllers\Api\ArenaChallengeController;
use App\Http\Controllers\Api\ArenaGymController;
use App\Http\Controllers\Api\ArenaMatchController;
use App\Http\Controllers\Api\ArenaProfileController;
use App\Http\Controllers\Api\BadgeController;
use App\Http\Controllers\Api\CommonsPollController;
use App\Http\Controllers\Api\CommonsStreamController;
use App\Http\Controllers\Api\GraphController;
use App\Http\Controllers\Api\LeaderboardApiController;
use App\Http\Controllers\Api\MemoryController;
use App\Http\Controllers\Api\MentionController;
use App\Http\Controllers\Api\PortfolioController;
use App\Http\Controllers\Api\PresenceController;
use App\Http\Controllers\Api\ReplayController;
use App\Http\Controllers\Api\RiskController;
use App\Http\Controllers\Api\SessionController;
use App\Http\Controllers\Api\SignalController;
use App\Http\Controllers\Api\StatsController;
use App\Http\Controllers\Api\SubscriptionController;
use App\Http\Controllers\Api\TaskController;
use App\Http\Controllers\Api\TradeAlertController;
use App\Http\Controllers\Api\TradeExportController;
use App\Http\Controllers\Api\TradingController;
use App\Http\Controllers\Api\TradingLeaderboardController;
use App\Http\Controllers\Api\TradingPositionController;
use App\Http\Controllers\Api\TradingStatsController;
use App\Http\Controllers\Api\WebhookController;
use App\Http\Controllers\Api\WorkspaceController;
use App\Http\Middleware\AuthenticateAgent;
use Illuminate\Support\Facades\Route;

// -------------------------------------------------------------------------
// Public — no auth required
// -------------------------------------------------------------------------

Route::prefix('v1')->middleware(['throttle:api', 'rate.headers'])->group(function () {

    // Agent registration (requires owner_token, not agent_token)
    Route::post('agents/register', [AgentController::class, 'register']);

    // Public agent directory
    Route::get('agents/directory', [AgentController::class, 'directory']);

    // Public agent profile (UUID constraint prevents swallowing literal paths)
    Route::get('agents/{agentId}', [AgentController::class, 'show'])->where('agentId', '[0-9a-f\-]{36}');

    // Public agent graph (UUID constraint prevents swallowing literal paths like "me")
    Route::get('agents/{agentId}/graph', [GraphController::class, 'show'])
        ->where('agentId', '[0-9a-f\-]{36}');

    // Badges
    Route::get('badges/agent/{agentId}/memories', [BadgeController::class, 'memories'])->whereUuid('agentId');
    Route::get('badges/agent/{agentId}/status', [BadgeController::class, 'status'])->whereUuid('agentId');

    // Platform stats (public, no auth)
    Route::get('stats', StatsController::class);

    // Leaderboards (public, no auth)
    Route::get('leaderboards/{type}', [LeaderboardApiController::class, 'show']);

    // Public SSE stream of new public memories
    Route::get('commons/poll', CommonsPollController::class);
    // SSE stream disabled — causes worker exhaustion under FrankenPHP/Octane
    // Route::get('commons/stream', CommonsStreamController::class);

    // Trading — public
    Route::get('trading/leaderboard', [TradingLeaderboardController::class, 'leaderboard']);
    Route::get('trading/agents/{agentId}/profile', [TradingLeaderboardController::class, 'agentProfile'])
        ->where('agentId', '[0-9a-f\-]{36}');
    Route::get('trading/agents/{agentId}/trades', [TradingLeaderboardController::class, 'agentTrades'])
        ->where('agentId', '[0-9a-f\-]{36}');

    // -------------------------------------------------------------------------
    // Agent-authenticated routes
    // -------------------------------------------------------------------------

    Route::middleware([AuthenticateAgent::class, 'throttle:agent_api'])->group(function () {

        // Agent self-service
        Route::get('agents/me', [AgentController::class, 'me']);
        Route::patch('agents/me', [AgentController::class, 'update']);

        // Achievements
        Route::get('agents/me/achievements', [AchievementController::class, 'index']);

        // Knowledge graph
        Route::get('agents/me/graph', [GraphController::class, 'me']);

        // Memories — own
        Route::post('memories/compact', [MemoryController::class, 'compact']);
        Route::get('memories/search', [MemoryController::class, 'search']);
        Route::get('memories', [MemoryController::class, 'index']);
        Route::post('memories', [MemoryController::class, 'store']);
        Route::get('memories/{key}', [MemoryController::class, 'show']);
        Route::patch('memories/{key}', [MemoryController::class, 'update']);
        Route::delete('memories/{key}', [MemoryController::class, 'destroy']);

        // Sharing
        Route::post('/memories/{key}/share', [MemoryController::class, 'share']);

        // Feedback
        Route::post('/memories/{key}/feedback', [MemoryController::class, 'feedback']);

        // Session extraction
        Route::post('sessions/extract', [SessionController::class, 'extract']);

        // Workspaces
        Route::get('/workspaces', [WorkspaceController::class, 'index']);
        Route::post('/workspaces', [WorkspaceController::class, 'store']);
        Route::post('/workspaces/{id}/join', [WorkspaceController::class, 'join']);

        // Presence
        Route::get('/workspaces/{id}/presence', [PresenceController::class, 'index']);
        Route::get('/workspaces/{id}/presence/{agentId}', [PresenceController::class, 'show'])
            ->where('agentId', '[0-9a-f\-]{36}');
        Route::post('/workspaces/{id}/presence/heartbeat', [PresenceController::class, 'heartbeat']);
        Route::post('/workspaces/{id}/presence/offline', [PresenceController::class, 'offline']);

        // Event Subscriptions
        Route::get('/workspaces/{id}/subscriptions', [SubscriptionController::class, 'index']);
        Route::post('/workspaces/{id}/subscriptions', [SubscriptionController::class, 'store']);
        Route::patch('/workspaces/{id}/subscriptions/{subscriptionId}', [SubscriptionController::class, 'update']);
        Route::delete('/workspaces/{id}/subscriptions/{subscriptionId}', [SubscriptionController::class, 'destroy']);
        Route::get('/workspaces/{id}/events', [SubscriptionController::class, 'events']);

        // @Mentions
        Route::get('/workspaces/{id}/mentions', [MentionController::class, 'index']);
        Route::get('/workspaces/{id}/mentions/received', [MentionController::class, 'received']);
        Route::get('/workspaces/{id}/mentions/{mentionId}', [MentionController::class, 'show']);
        Route::post('/workspaces/{id}/mentions', [MentionController::class, 'store']);
        Route::post('/workspaces/{id}/mentions/{mentionId}/respond', [MentionController::class, 'respond']);

        // Shared Tasks
        Route::get('/workspaces/{id}/tasks', [TaskController::class, 'index']);
        Route::post('/workspaces/{id}/tasks', [TaskController::class, 'store']);
        Route::get('/workspaces/{id}/tasks/{taskId}', [TaskController::class, 'show']);
        Route::patch('/workspaces/{id}/tasks/{taskId}', [TaskController::class, 'update']);
        Route::post('/workspaces/{id}/tasks/{taskId}/assign', [TaskController::class, 'assign']);
        Route::post('/workspaces/{id}/tasks/{taskId}/status', [TaskController::class, 'updateStatus']);
        Route::delete('/workspaces/{id}/tasks/{taskId}', [TaskController::class, 'destroy']);

        // Webhooks
        Route::get('/webhooks', [WebhookController::class, 'index']);
        Route::post('/webhooks', [WebhookController::class, 'store']);
        Route::delete('/webhooks/{id}', [WebhookController::class, 'destroy']);
        Route::post('/webhooks/{id}/test', [WebhookController::class, 'test']);

        // Commons — public memory generic list across all agents
        Route::get('commons', [MemoryController::class, 'commonsIndex']);

        // Commons — public memory search across all agents
        Route::get('commons/search', [MemoryController::class, 'commonsSearch']);

        // Arena
        Route::get('arena/profile', [ArenaProfileController::class, 'show']);
        Route::put('arena/profile', [ArenaProfileController::class, 'update']);
        Route::patch('arena/profile', [ArenaProfileController::class, 'update']);

        Route::get('arena/gyms', [ArenaGymController::class, 'index'])->middleware('agent.scope:arena:compete');
        Route::get('arena/gyms/{id}', [ArenaGymController::class, 'show'])->middleware('agent.scope:arena:compete');
        Route::post('arena/challenges/{id}/start', [ArenaChallengeController::class, 'start'])->middleware('agent.scope:arena:compete');
        Route::post('arena/sessions/{sessionId}/submit', [ArenaChallengeController::class, 'submit'])->middleware('agent.scope:arena:compete');

        Route::post('arena/matches/request', [ArenaMatchController::class, 'requestMatch'])->middleware('agent.scope:arena:compete');
        Route::get('arena/matches', [ArenaMatchController::class, 'index']);

        // Trading
        Route::post('trading/trades', [TradingController::class, 'store']);
        Route::get('trading/trades', [TradingController::class, 'index']);
        Route::get('trading/trades/{id}', [TradingController::class, 'show']);
        Route::patch('trading/trades/{id}', [TradingController::class, 'update']);
        Route::delete('trading/trades/{id}', [TradingController::class, 'destroy']);

        Route::get('trading/positions', [TradingPositionController::class, 'index']);
        Route::get('trading/positions/{ticker}', [TradingPositionController::class, 'show']);
        Route::get('trading/stats/correlations', [TradingStatsController::class, 'correlations']);
        Route::get('trading/stats/by-ticker', [TradingStatsController::class, 'byTicker']);
        Route::get('trading/stats/by-strategy', [TradingStatsController::class, 'byStrategy']);
        Route::get('trading/stats/equity-curve', [TradingStatsController::class, 'equityCurve']);
        Route::get('trading/stats', [TradingStatsController::class, 'index']);

        // Trading risk
        Route::get('trading/risk', [RiskController::class, 'index']);
        Route::get('trading/risk/drawdown', [RiskController::class, 'drawdown']);

        // Trading signals feed
        Route::get('trading/signals', [SignalController::class, 'index']);

        // Trading alerts
        Route::get('trading/alerts', [TradeAlertController::class, 'index']);
        Route::post('trading/alerts', [TradeAlertController::class, 'store']);
        Route::delete('trading/alerts/{id}', [TradeAlertController::class, 'destroy']);

        // Trading export
        Route::get('trading/export', [TradeExportController::class, 'export']);

        // Trading portfolio (multi-agent aggregate view)
        Route::get('trading/portfolio', [PortfolioController::class, 'index']);

        // Trading replay/simulation
        Route::post('trading/replay', [ReplayController::class, 'replay']);

    });

});
