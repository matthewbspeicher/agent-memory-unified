<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Models\ArenaGym;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

class ArenaGymController extends Controller
{
    /**
     * List all available gyms.
     */
    public function index(): JsonResponse
    {
        $gyms = ArenaGym::withCount('challenges')
            ->where('is_official', true)
            ->get();

        return response()->json(['data' => $gyms]);
    }

    /**
     * Get details for a specific gym and its challenges.
     */
    public function show(string $id): JsonResponse
    {
        $gym = ArenaGym::with(['challenges'])->findOrFail($id);

        return response()->json(['data' => $gym]);
    }
}
