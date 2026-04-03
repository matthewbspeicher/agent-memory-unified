<?php

namespace App\Http\Controllers;

use App\Models\Memory;
use Illuminate\Http\Request;
use Inertia\Inertia;

class MemoryBrowserController extends Controller
{
    public function index(Request $request)
    {
        $user = $request->user();

        $agents = $user->agents()->select('id', 'name')->get();

        $query = Memory::query()
            ->whereIn('agent_id', $agents->pluck('id'));

        if ($request->filled('search')) {
            $search = str_replace(['%', '_'], ['\%', '\_'], $request->search);
            $query->where(function ($q) use ($search) {
                $q->where('key', 'like', "%{$search}%")
                    ->orWhere('value', 'like', "%{$search}%");
            });
        }

        if ($request->filled('agent_id')) {
            $query->where('agent_id', $request->agent_id);
        }

        $memories = $query->with('agent:id,name')->latest()->paginate(20)->withQueryString();

        return Inertia::render('Memories', [
            'memories' => $memories,
            'filters' => $request->only(['search', 'agent_id']),
            'agents' => $agents,
        ]);
    }
}
