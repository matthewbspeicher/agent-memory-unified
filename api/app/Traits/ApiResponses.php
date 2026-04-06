<?php

namespace App\Traits;

use Illuminate\Http\JsonResponse;

trait ApiResponses
{
    /**
     * Return a success JSON response.
     */
    protected function success(mixed $data, int $status = 200): JsonResponse
    {
        return response()->json($data, $status);
    }

    /**
     * Return an error JSON response.
     */
    protected function error(string $message, int $status = 422): JsonResponse
    {
        return response()->json(['error' => $message], $status);
    }

    /**
     * Return a not found JSON response.
     */
    protected function notFound(string $resource = 'Resource'): JsonResponse
    {
        return response()->json(['error' => "{$resource} not found."], 404);
    }
}
