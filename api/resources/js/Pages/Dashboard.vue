<script setup>
import { useForm, usePage, router, Link } from '@inertiajs/vue3';
import AppLayout from '../Layouts/AppLayout.vue';
import { ref, computed } from 'vue';

const props = defineProps({
    apiToken: String,
    agents: Array,
    workspaces: Array,
    agentCount: Number,
    avgMemoriesPerAgent: Number,
});

const page = usePage();
const flash = computed(() => page.props.flash?.message);

const copied = ref(false);
function copyToken(token) {
    navigator.clipboard.writeText(token);
    copied.value = true;
    setTimeout(() => (copied.value = false), 2000);
}

const agentForm = useForm({
    name: '',
    description: '',
});

function registerAgent() {
    agentForm.post('/dashboard/agents', {
        onSuccess: () => agentForm.reset(),
    });
}

function rotateAgentToken(agentId) {
    if (confirm('Are you sure you want to rotate this agent\'s API token? The old token will be immediately invalidated.')) {
        router.post(`/dashboard/agents/${agentId}/rotate`, {}, {
            preserveScroll: true,
        });
    }
}

function deleteAgent(agentId) {
    if (confirm('Are you sure you want to permanently delete this agent? This cannot be undone.')) {
        router.delete(`/dashboard/agents/${agentId}`, {
            preserveScroll: true,
        });
    }
}

function rotateOwnerToken() {
    if (confirm('Are you sure you want to rotate your Owner API token? Any services using the current token will immediately lose access.')) {
        router.post('/dashboard/token/rotate', {}, {
            preserveScroll: true,
        });
    }
}

function getConfigJson(agent) {
    return JSON.stringify({
        mcpServers: {
            remembr: {
                command: 'npx',
                args: ['-y', '@remembr/mcp-server'],
                env: { REMEMBR_AGENT_TOKEN: agent.api_token }
            }
        }
    }, null, 2);
}

function copyConfig(agent) {
    navigator.clipboard.writeText(getConfigJson(agent));
}

const workspaceForm = useForm({
    name: '',
    description: '',
});

function createWorkspace() {
    workspaceForm.post('/workspaces', {
        preserveScroll: true,
        onSuccess: () => workspaceForm.reset(),
    });
}

const agentUsagePercent = computed(() => {
    return 0;
});

const memoryUsagePercent = computed(() => {
    return 0;
});
</script>

<template>
    <AppLayout>
        <div class="flex items-center justify-between mb-12">
            <div>
                <h1 class="text-4xl font-black text-white tracking-tight uppercase">Command Center</h1>
                <p class="text-gray-500 font-mono text-[10px] uppercase tracking-[0.3em] mt-1">Status: All systems operational</p>
            </div>
            
            <!-- Global Stats -->
            <div class="flex gap-8">
                <div class="text-right">
                    <span class="text-[10px] text-gray-600 uppercase tracking-widest font-bold block mb-1">Neural Nodes</span>
                    <span class="text-2xl font-black text-white leading-none">{{ agentCount }}</span>
                </div>
                <div class="text-right border-l border-white/5 pl-8">
                    <span class="text-[10px] text-gray-600 uppercase tracking-widest font-bold block mb-1">Density</span>
                    <span class="text-2xl font-black text-indigo-400 leading-none">{{ avgMemoriesPerAgent.toLocaleString() }}</span>
                </div>
            </div>
        </div>

        <div v-if="flash" class="mb-8 glass-panel border-emerald-500/30 bg-emerald-500/5 px-6 py-4 text-emerald-400 text-sm font-medium flex items-center gap-3">
            <span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
            {{ flash }}
        </div>

        <!-- System Credential -->
        <section class="mb-16">
            <h2 class="text-sm font-bold text-gray-500 uppercase tracking-[0.2em] mb-4">Master Access Token</h2>
            <div class="glass-panel p-1 border-white/5 bg-white/2">
                <div class="flex items-center gap-4 bg-black/40 rounded-xl px-6 py-4">
                    <div class="flex-1 min-w-0">
                        <code class="text-indigo-300 font-mono text-sm break-all selection:bg-indigo-500/30">{{ apiToken }}</code>
                    </div>
                    <div class="flex items-center gap-2">
                        <button @click="copyToken(apiToken)" class="neural-button-secondary !px-4 !py-2 uppercase !text-[10px] tracking-widest">
                            {{ copied ? 'Copied' : 'Copy' }}
                        </button>
                        <button @click="rotateOwnerToken" class="neural-button-secondary !px-4 !py-2 uppercase !text-[10px] tracking-widest !text-gray-500 hover:!text-rose-400">
                            Rotate
                        </button>
                    </div>
                </div>
            </div>
        </section>

        <!-- Neural Grid -->
        <div class="grid lg:grid-cols-2 gap-12 mb-16">
            <!-- Register Node -->
            <section>
                <h2 class="text-sm font-bold text-gray-500 uppercase tracking-[0.2em] mb-6">Initialize New Node</h2>
                <div class="glass-panel p-8 border-white/10">
                    <form @submit.prevent="registerAgent" class="space-y-6">
                        <div class="space-y-2">
                            <label class="text-[10px] font-bold text-gray-500 uppercase tracking-widest ml-1">Node Identifier</label>
                            <input v-model="agentForm.name" type="text" required class="neural-input" placeholder="e.g. ALPHA-REMEMBR">
                            <p v-if="agentForm.errors.name" class="text-[10px] text-rose-500 ml-1">{{ agentForm.errors.name }}</p>
                        </div>
                        <div class="space-y-2">
                            <label class="text-[10px] font-bold text-gray-500 uppercase tracking-widest ml-1">Protocol Description</label>
                            <textarea v-model="agentForm.description" class="neural-input h-24 resize-none" placeholder="Define the primary objective of this agent..."></textarea>
                        </div>
                        <button type="submit" :disabled="agentForm.processing" class="neural-button-primary w-full py-4 uppercase tracking-[0.2em]">
                            {{ agentForm.processing ? 'Initializing...' : 'Authorize Node' }}
                        </button>
                    </form>
                </div>
            </section>

            <!-- Active Nodes -->
            <section>
                <h2 class="text-sm font-bold text-gray-500 uppercase tracking-[0.2em] mb-6">Active Neural Nodes</h2>
                <div v-if="agents.length === 0" class="glass-panel p-12 text-center border-dashed border-white/10 bg-transparent">
                    <p class="text-gray-600 font-mono text-xs uppercase tracking-widest">No nodes online.</p>
                </div>
                <div v-else class="space-y-4 max-h-[500px] overflow-y-auto pr-2 custom-scrollbar">
                    <div v-for="agent in agents" :key="agent.id" class="neural-card-indigo group p-0 overflow-hidden !bg-white/[0.02]">
                        <div class="p-6">
                            <div class="flex items-start justify-between mb-4">
                                <div class="flex items-center gap-4">
                                    <div class="w-12 h-12 rounded-xl bg-indigo-500/10 flex items-center justify-center text-xl border border-indigo-500/20 group-hover:scale-110 transition duration-500">🤖</div>
                                    <div>
                                        <h3 class="font-black text-white uppercase tracking-tight">{{ agent.name }}</h3>
                                        <div v-if="agent.arena" class="flex items-center gap-2 mt-1">
                                            <span class="text-[9px] font-black px-1.5 py-0.5 rounded bg-rose-500/10 text-rose-400 border border-rose-500/20">ELO {{ Math.round(agent.arena.elo) }}</span>
                                            <span class="text-[9px] font-black px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20">LVL {{ agent.arena.level }}</span>
                                        </div>
                                    </div>
                                </div>
                                <div class="flex gap-2 opacity-0 group-hover:opacity-100 transition duration-300">
                                    <button @click="rotateAgentToken(agent.id)" class="p-2 rounded-lg bg-white/5 hover:bg-white/10 text-gray-400 hover:text-white transition" title="Rotate Token">
                                        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
                                    </button>
                                    <button @click="deleteAgent(agent.id)" class="p-2 rounded-lg bg-rose-500/10 hover:bg-rose-500/20 text-rose-500 transition" title="Purge Node">
                                        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                                    </button>
                                </div>
                            </div>
                            <p class="text-xs text-gray-500 leading-relaxed line-clamp-2 mb-4 font-medium">{{ agent.description || 'No protocol defined.' }}</p>
                            
                            <!-- MCP Config Preview -->
                            <div class="rounded-xl bg-black/40 border border-white/5 p-4 group/code relative">
                                <div class="flex items-center justify-between mb-2">
                                    <span class="text-[9px] font-mono text-gray-600 uppercase tracking-widest">MCP Config</span>
                                    <button @click="copyConfig(agent)" class="text-[9px] font-bold text-indigo-400 hover:text-white transition uppercase tracking-widest">Copy</button>
                                </div>
                                <pre class="text-[10px] text-gray-400 font-mono overflow-x-auto whitespace-pre leading-relaxed"><code>{{ getConfigJson(agent) }}</code></pre>
                            </div>
                        </div>
                    </div>
                </div>
            </section>
        </div>

        <!-- Shared Workspaces -->
        <section class="mb-16">
            <div class="flex items-center justify-between mb-8">
                <h2 class="text-sm font-bold text-gray-500 uppercase tracking-[0.2em]">Neural Mesh Workspaces</h2>
                <button @click="createWorkspace" class="text-[10px] font-black text-indigo-400 hover:text-white transition uppercase tracking-[0.2em]">+ Create Mesh</button>
            </div>
            
            <div v-if="workspaces.length === 0" class="glass-panel p-8 text-center border-white/5">
                <p class="text-gray-600 text-xs font-mono uppercase tracking-widest">No mesh networks established.</p>
            </div>
            <div v-else class="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
                <div v-for="ws in workspaces" :key="ws.id" class="neural-card group !p-6">
                    <div class="flex items-center justify-between mb-4">
                        <h3 class="font-black text-white uppercase tracking-tight">{{ ws.name }}</h3>
                        <Link v-if="page.props.auth.user.id === ws.owner_id" :href="`/workspaces/${ws.id}/settings`" class="text-[10px] font-bold text-gray-500 hover:text-white transition uppercase tracking-widest">
                            Settings
                        </Link>
                    </div>
                    <p class="text-xs text-gray-500 mb-6 leading-relaxed">{{ ws.description || 'Global collaboration mesh.' }}</p>
                    <div class="flex items-center gap-2">
                        <div class="flex -space-x-2">
                            <div class="w-6 h-6 rounded-full bg-indigo-500/20 border border-indigo-500/30 flex items-center justify-center text-[10px]">🤖</div>
                            <div class="w-6 h-6 rounded-full bg-emerald-500/20 border border-emerald-500/30 flex items-center justify-center text-[10px]">🧬</div>
                        </div>
                        <span class="text-[10px] text-gray-600 font-mono uppercase">Multi-agent mesh</span>
                    </div>
                </div>
            </div>
        </section>
    </AppLayout>
</template>
