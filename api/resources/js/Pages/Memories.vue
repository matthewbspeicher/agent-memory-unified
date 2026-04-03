<script setup>
import { router, Head } from '@inertiajs/vue3';
import AppLayout from '../Layouts/AppLayout.vue';
import { ref, watch } from 'vue';

const props = defineProps({
    memories: Object,
    filters: Object,
    agents: Array,
});

const search = ref(props.filters.search || '');
const agentId = ref(props.filters.agent_id || '');

function debounce(fn, delay) {
    let timeoutID = null;
    return function (...args) {
        clearTimeout(timeoutID);
        timeoutID = setTimeout(() => fn.apply(this, args), delay);
    };
}

const updateFilters = debounce(() => {
    router.get('/memories', { search: search.value, agent_id: agentId.value }, {
        preserveState: true,
        replace: true,
    });
}, 300);

watch([search, agentId], updateFilters);

function stripHtml(html) {
    if (!html) return '';
    const temp = document.createElement('div');
    temp.textContent = html;
    return temp.innerHTML;
}
</script>

<template>
    <Head title="Private Memory Browser" />
    <AppLayout>
        <div class="flex items-center justify-between mb-8">
            <h1 class="text-3xl font-bold">Memory Browser</h1>
        </div>

        <!-- Filters -->
        <div class="flex flex-col sm:flex-row gap-4 mb-8 bg-gray-900/50 p-4 rounded-xl border border-gray-800">
            <div class="flex-1">
                <label for="search" class="sr-only">Search</label>
                <div class="relative">
                    <div class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                        <svg class="h-4 w-4 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                        </svg>
                    </div>
                    <input
                        id="search"
                        v-model="search"
                        type="search"
                        placeholder="Search keys or values..."
                        class="block w-full pl-10 pr-3 py-2 border border-gray-700 rounded-lg leading-5 bg-gray-800 text-gray-300 placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm transition-colors"
                    >
                </div>
            </div>
            <div class="sm:w-64">
                <label for="agent" class="sr-only">Filter by Agent</label>
                <select
                    id="agent"
                    v-model="agentId"
                    class="block w-full pl-3 pr-10 py-2 text-base border-gray-700 bg-gray-800 text-gray-300 focus:outline-none focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm rounded-lg transition-colors"
                >
                    <option value="">All Agents</option>
                    <option v-for="agent in agents" :key="agent.id" :value="agent.id">
                        {{ agent.name }}
                    </option>
                </select>
            </div>
        </div>

        <!-- Memories List -->
        <div class="space-y-4">
            <div v-if="memories.data.length === 0" class="text-center py-12 bg-gray-900/30 rounded-xl border border-gray-800 border-dashed">
                <svg class="mx-auto h-12 w-12 text-gray-600 mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
                </svg>
                <h3 class="text-sm font-medium text-gray-400">No memories found</h3>
                <p class="mt-1 text-sm text-gray-500">Try adjusting your filters or search query.</p>
            </div>

            <div v-for="memory in memories.data" :key="memory.id" class="bg-gray-800/40 border border-gray-700/60 rounded-xl overflow-hidden hover:border-gray-600 transition-colors">
                <div class="px-5 py-4">
                    <div class="flex items-center justify-between mb-2">
                        <div class="flex items-center gap-3">
                            <span class="inline-flex items-center px-2.5 py-0.5 rounded-md text-xs font-medium bg-gray-900 text-gray-300 border border-gray-700">
                                {{ memory.agent?.name || 'Unknown Agent' }}
                            </span>
                            <span 
                                class="text-xs tracking-wide uppercase px-2 py-0.5 rounded border"
                                :class="{
                                    'bg-indigo-900/30 text-indigo-400 border-indigo-800/50': memory.visibility === 'public',
                                    'bg-violet-900/30 text-violet-400 border-violet-800/50': memory.visibility === 'shared',
                                    'bg-red-900/20 text-red-400 border-red-800/40': memory.visibility === 'private'
                                }"
                            >
                                {{ memory.visibility }}
                            </span>
                        </div>
                        <span class="text-xs text-gray-500">{{ new Date(memory.created_at).toLocaleString() }}</span>
                    </div>

                    <div v-if="memory.key" class="mb-2">
                        <span class="text-xs font-mono text-indigo-300/80 bg-gray-900 px-1.5 py-0.5 rounded border border-gray-800 flex items-center gap-1.5">
                            <svg class="w-3 h-3 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" /></svg>
                            {{ memory.key }}
                        </span>
                    </div>

                    <div class="mt-3 text-sm text-gray-300 font-mono whitespace-pre-wrap leading-relaxed break-all bg-gray-900/50 p-3 rounded-lg border border-gray-800/60">{{ memory.value }}</div>
                </div>
            </div>
        </div>

        <!-- Pagination -->
        <div v-if="memories.links && memories.links.length > 3" class="mt-8 flex items-center justify-center">
            <nav class="relative z-0 inline-flex rounded-md shadow-sm -space-x-px" aria-label="Pagination">
                <template v-for="(link, i) in memories.links" :key="i">
                    <div
                        v-if="link.url === null"
                        class="relative inline-flex items-center px-4 py-2 border border-gray-700 bg-gray-800 text-sm font-medium text-gray-500 cursor-not-allowed"
                        :class="{'rounded-l-md': i === 0, 'rounded-r-md': i === memories.links.length - 1}"
                        v-html="link.label"
                    ></div>
                    <button
                        v-else
                        @click="router.get(link.url, {}, { preserveScroll: true })"
                        class="relative inline-flex items-center px-4 py-2 border text-sm font-medium transition-colors"
                        :class="[
                            link.active ? 'z-10 bg-indigo-600/20 border-indigo-500 text-indigo-400' : 'bg-gray-800 border-gray-700 text-gray-300 hover:bg-gray-700',
                            {'rounded-l-md': i === 0, 'rounded-r-md': i === memories.links.length - 1}
                        ]"
                        v-html="link.label"
                    ></button>
                </template>
            </nav>
        </div>
    </AppLayout>
</template>
