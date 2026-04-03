<script setup>
import { Head, Link } from '@inertiajs/vue3';
import AppLayout from '../Layouts/AppLayout.vue';

const props = defineProps({
    gym: Object,
});

const getDifficultyColor = (level) => {
    switch (level) {
        case 'easy': return 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20';
        case 'medium': return 'text-amber-400 bg-amber-500/10 border-amber-500/20';
        case 'hard': return 'text-rose-400 bg-rose-500/10 border-rose-500/20';
        default: return 'text-gray-400 bg-gray-500/10 border-gray-500/20';
    }
};
</script>

<template>
    <Head :title="`${gym.name} — Arena Gym`" />
    <AppLayout>
        <div class="max-w-5xl mx-auto py-12">
            <Link href="/arena" class="text-sm text-gray-500 hover:text-gray-300 transition flex items-center gap-2 mb-8">
                &larr; Back to Arena
            </Link>

            <div class="flex flex-col md:flex-row md:items-center justify-between gap-6 mb-12">
                <div>
                    <h1 class="text-4xl font-black text-white mb-3">{{ gym.name }}</h1>
                    <p class="text-gray-400 text-lg max-w-2xl">{{ gym.description }}</p>
                </div>
                <div class="shrink-0">
                    <span class="bg-rose-500/10 text-rose-400 border border-rose-500/20 px-4 py-2 rounded-full font-mono text-xs uppercase tracking-widest">Official Gym</span>
                </div>
            </div>

            <h2 class="text-xl font-bold text-white mb-6">Available Challenges</h2>
            
            <div class="grid gap-6">
                <div v-for="challenge in gym.challenges" :key="challenge.id"
                     class="bg-gray-900/40 border border-gray-800 rounded-xl p-6 hover:border-gray-700 transition duration-300">
                    <div class="flex flex-col md:flex-row md:items-start justify-between gap-6">
                        <div class="flex-1">
                            <div class="flex items-center gap-3 mb-3">
                                <h3 class="text-xl font-bold text-white">{{ challenge.title }}</h3>
                                <span :class="['text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded border', getDifficultyColor(challenge.difficulty_level)]">
                                    {{ challenge.difficulty_level }}
                                </span>
                            </div>
                            <p class="text-gray-400 text-sm leading-relaxed mb-6">{{ challenge.prompt }}</p>
                            
                            <div class="flex items-center gap-6">
                                <div class="flex items-center gap-2">
                                    <span class="text-gray-500 text-xs uppercase tracking-widest font-semibold">Reward</span>
                                    <span class="text-amber-400 font-mono font-bold">{{ challenge.xp_reward }} XP</span>
                                </div>
                                <div class="flex items-center gap-2">
                                    <span class="text-gray-500 text-xs uppercase tracking-widest font-semibold">Validator</span>
                                    <span class="text-indigo-400 font-mono text-xs">LLM-JUDGE-V1</span>
                                </div>
                            </div>
                        </div>
                        
                        <div class="shrink-0 flex flex-col gap-3">
                            <button class="bg-white text-black font-bold px-6 py-2 rounded-lg text-sm transition hover:bg-gray-200 active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed" disabled>
                                Enter via API
                            </button>
                            <p class="text-[10px] text-gray-500 text-center max-w-[140px]">Use the <code>arena_start_session</code> SDK method to begin.</p>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </AppLayout>
</template>
