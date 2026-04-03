<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Models\Agent;
use Illuminate\Http\Response;
use Illuminate\Support\Facades\Cache;

class BadgeController extends Controller
{
    public function memories(string $agentId): Response
    {
        $agent = Agent::find($agentId);
        if (! $agent) {
            abort(404);
        }

        $count = Cache::remember("badge_memories_{$agent->id}", 300, function () use ($agent) {
            return $agent->memories()->count();
        });

        $svg = $this->generateSvg('memories', (string) $count, '#3b82f6'); // blue-500

        return response($svg)->header('Content-Type', 'image/svg+xml');
    }

    public function status(string $agentId): Response
    {
        $agent = Agent::find($agentId);
        if (! $agent) {
            abort(404);
        }

        $isActive = Cache::remember("badge_status_{$agent->id}", 300, function () use ($agent) {
            // "Active" if seen in the last 24 hours
            return $agent->last_seen_at && $agent->last_seen_at->gt(now()->subDay());
        });

        $statusText = $isActive ? 'active' : 'inactive';
        $color = $isActive ? '#22c55e' : '#ef4444'; // green-500 : red-500

        $svg = $this->generateSvg('status', $statusText, $color);

        return response($svg)->header('Content-Type', 'image/svg+xml');
    }

    private function generateSvg(string $label, string $value, string $color): string
    {
        $labelWidth = strlen($label) * 8 + 10;
        $valueWidth = strlen($value) * 8 + 10;
        $totalWidth = $labelWidth + $valueWidth;

        return <<<SVG
<svg xmlns="http://www.w3.org/2000/svg" width="{$totalWidth}" height="20">
    <linearGradient id="b" x2="0" y2="100%">
        <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
        <stop offset="1" stop-opacity=".1"/>
    </linearGradient>
    <mask id="a">
        <rect width="{$totalWidth}" height="20" rx="3" fill="#fff"/>
    </mask>
    <g mask="url(#a)">
        <path fill="#555" d="M0 0h{$labelWidth}v20H0z"/>
        <path fill="{$color}" d="M{$labelWidth} 0h{$valueWidth}v20H{$labelWidth}z"/>
        <path fill="url(#b)" d="M0 0h{$totalWidth}v20H0z"/>
    </g>
    <g fill="#fff" text-anchor="middle" font-family="DejaVu Sans,Verdana,Geneva,sans-serif" font-size="11">
        <text x="{($labelWidth / 2)}" y="15" fill="#010101" fill-opacity=".3">{$label}</text>
        <text x="{($labelWidth / 2)}" y="14">{$label}</text>
        <text x="{($labelWidth + $valueWidth / 2)}" y="15" fill="#010101" fill-opacity=".3">{$value}</text>
        <text x="{($labelWidth + $valueWidth / 2)}" y="14">{$value}</text>
    </g>
</svg>
SVG;
    }
}
