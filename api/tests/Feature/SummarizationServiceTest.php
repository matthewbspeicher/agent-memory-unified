<?php

use App\Models\Agent;
use App\Models\Memory;
use App\Services\SummarizationService;
use Illuminate\Http\Client\Request;
use Illuminate\Support\Facades\Http;

it('summarizes a collection of memories', function () {
    $agent = Agent::factory()->make(['name' => 'TestAgent']);

    $memories = collect([
        new Memory(['key' => 'fact1', 'value' => 'The user likes dogs.']),
        new Memory(['key' => 'fact2', 'value' => 'The user really enjoys golden retrievers.']),
        new Memory(['key' => 'fact3', 'value' => 'The user has a dog named Max.']),
    ]);

    Http::fake([
        'generativelanguage.googleapis.com/*' => Http::response([
            'candidates' => [
                [
                    'content' => [
                        'parts' => [
                            ['text' => 'The user loves dogs, specifically golden retrievers, and has one named Max.'],
                        ],
                    ],
                ],
            ],
        ], 200),
    ]);

    $service = new SummarizationService;
    $summary = $service->summarize($memories, $agent);

    expect($summary)->toBe('The user loves dogs, specifically golden retrievers, and has one named Max.');

    Http::assertSent(function (Request $request) {
        return str_contains($request->url(), 'generateContent');
    });
});
