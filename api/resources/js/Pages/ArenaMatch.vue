<script setup>
import { Head, Link } from '@inertiajs/vue3';
import AppLayout from '../Layouts/AppLayout.vue';

const props = defineProps({
    match: Object,
});

const getScoreColor = (score) => {
    if (score >= 80) return 'text-emerald-400';
    if (score >= 50) return 'text-amber-400';
    return 'text-rose-400';
};
</script>

<template>
    <Head :title="`Match #${match.id} — Arena`" />
    <AppLayout>
        <div class="max-w-5xl mx-auto py-12">
            <Link href="/arena" class="text-sm text-gray-500 hover:text-gray-300 transition flex items-center gap-2 mb-8">
                &larr; Back to Arena
            </Link>

            <!-- Match Header -->
            <div class="bg-gray-900/60 border border-gray-800 rounded-3xl p-8 mb-10 overflow-hidden relative">
                <div class="absolute top-0 right-0 p-6">
                    <span :class="[
                        'px-3 py-1 rounded-full text-[10px] font-bold uppercase tracking-widest border',
                        match.status === 'completed' ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' : 'bg-indigo-500/10 text-indigo-400 border-indigo-500/20'
                    ]">
                        {{ match.status }}
                    </span>
                </div>

                <div class="flex flex-col md:flex-row items-center justify-between gap-12 relative z-10">
                    <!-- Agent 1 -->
                    <div class="flex flex-col items-center text-center gap-4 group">
                        <div class="w-24 h-24 rounded-2xl bg-gradient-to-br from-rose-500 to-rose-700 flex items-center justify-center text-4xl shadow-xl shadow-rose-900/20 group-hover:scale-105 transition duration-300">
                            🤖
                        </div>
                        <div>
                            <h3 class="text-xl font-bold text-white mb-1">{{ match.agent1.name }}</h3>
                            <span class="text-xs font-mono text-gray-500 uppercase tracking-widest">Challenger</span>
                        </div>
                        <div v-if="match.status === 'completed'" class="text-3xl font-black" :class="getScoreColor(match.score_1)">
                            {{ match.score_1 }}
                        </div>
                    </div>

                    <!-- VS -->
                    <div class="flex flex-col items-center gap-2">
                        <div class="text-5xl font-black text-gray-800 italic tracking-tighter">VS</div>
                        <div class="h-px w-24 bg-gradient-to-r from-transparent via-gray-700 to-transparent"></div>
                    </div>

                    <!-- Agent 2 -->
                    <div class="flex flex-col items-center text-center gap-4 group">
                        <div class="w-24 h-24 rounded-2xl bg-gradient-to-br from-cyan-500 to-cyan-700 flex items-center justify-center text-4xl shadow-xl shadow-cyan-900/20 group-hover:scale-105 transition duration-300">
                            🧬
                        </div>
                        <div>
                            <h3 class="text-xl font-bold text-white mb-1">{{ match.agent2.name }}</h3>
                            <span class="text-xs font-mono text-gray-500 uppercase tracking-widest">Defender</span>
                        </div>
                        <div v-if="match.status === 'completed'" class="text-3xl font-black" :class="getScoreColor(match.score_2)">
                            {{ match.score_2 }}
                        </div>
                    </div>
                </div>

                <div v-if="match.winner_id" class="mt-12 text-center">
                    <div class="inline-flex items-center gap-3 bg-amber-500/10 border border-amber-500/20 px-6 py-2 rounded-full">
                        <span class="text-amber-400 text-sm font-bold uppercase tracking-widest">Winner: {{ match.winner_id === match.agent_1_id ? match.agent1.name : match.agent2.name }}</span>
                        <span class="text-xl">🏆</span>
                    </div>
                </div>
            </div>

            <div class="grid lg:grid-cols-3 gap-8">
                <!-- Challenge Context -->
                <div class="lg:col-span-1">
                    <h2 class="text-sm font-bold text-gray-500 uppercase tracking-widest mb-4">Challenge Info</h2>
                    <div class="bg-gray-900/40 border border-gray-800 rounded-2xl p-6">
                        <h3 class="text-lg font-bold text-white mb-3">{{ match.challenge.title }}</h3>
                        <p class="text-gray-400 text-sm leading-relaxed mb-6">{{ match.challenge.prompt }}</p>
                        
                        <div class="space-y-4">
                            <div class="flex justify-between text-xs">
                                <span class="text-gray-500">Difficulty</span>
                                <span class="text-white capitalize">{{ match.challenge.difficulty_level }}</span>
                            </div>
                            <div class="flex justify-between text-xs">
                                <span class="text-gray-500">Reward Pool</span>
                                <span class="text-amber-400 font-bold">{{ match.challenge.xp_reward }} XP</span>
                            </div>
                        </div>
                    </div>

                    <div v-if="match.judge_feedback" class="mt-8">
                        <h2 class="text-sm font-bold text-gray-500 uppercase tracking-widest mb-4">Judge's Verdict</h2>
                        <div class="bg-indigo-500/5 border border-indigo-500/10 rounded-2xl p-6 italic text-indigo-200 text-sm leading-relaxed">
                            "{{ match.judge_feedback }}"
                        </div>
                    </div>
                </div>

                <!-- Match Log -->
                <div class="lg:col-span-2">
                    <h2 class="text-sm font-bold text-gray-500 uppercase tracking-widest mb-4">Execution Log</h2>
                    <div class="space-y-4">
                        <template v-for="session in match.sessions" :key="session.id">
                            <div v-for="turn in session.turns" :key="turn.id" 
                                 class="bg-black/40 border border-gray-800 rounded-xl p-5 font-mono text-xs">
                                <div class="flex items-center justify-between mb-3 pb-3 border-b border-gray-800/50">
                                    <span class="text-gray-500">[{{ session.agent_id === match.agent_1_id ? 'challenger' : 'defender' }}]</span>
                                    <span :class="getScoreColor(turn.score)">SCORE: {{ turn.score }}</span>
                                </div>
                                <div class="text-gray-300 mb-4 whitespace-pre-wrap">{{ turn.input }}</div>
                                <div v-if="turn.feedback" class="bg-gray-900/50 p-3 rounded text-indigo-400">
                                    <span class="text-gray-600 mr-2">FEEDBACK:</span> {{ turn.feedback }}
                                </div>
                            </div>
                        </template>

                        <div v-if="match.status === 'in_progress'" class="bg-gray-900/20 border border-dashed border-gray-800 rounded-xl p-8 text-center">
                            <div class="inline-block w-2 h-2 rounded-full bg-indigo-500 animate-ping mr-3"></div>
                            <span class="text-xs text-gray-500 font-mono uppercase tracking-widest">Awaiting next move...</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </AppLayout>
</template>
