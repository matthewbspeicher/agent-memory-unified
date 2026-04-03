<script setup>
import { Head, Link, useForm } from '@inertiajs/vue3';
import AppLayout from '../Layouts/AppLayout.vue';
import { ref } from 'vue';

const props = defineProps({
    webhooks: Array,
    availableEvents: Array,
});

const showModal = ref(false);
const showingSecret = ref(null);

function toggleSecret(id) {
    if (showingSecret.value === id) {
        showingSecret.value = null;
    } else {
        showingSecret.value = id;
    }
}

const webhookForm = useForm({
    url: '',
    events: [],
    semantic_query: '',
});

function createWebhook() {
    webhookForm.post('/dashboard/webhooks', {
        onSuccess: () => {
            showModal.value = false;
            webhookForm.reset();
        },
    });
}

function deleteWebhook(id) {
    if (confirm('Are you sure you want to delete this webhook?')) {
        webhookForm.delete(`/dashboard/webhooks/${id}`);
    }
}

function testWebhook(id) {
    webhookForm.post(`/dashboard/webhooks/${id}/test`);
}
</script>

<template>
    <Head title="Webhook Management" />
    <AppLayout>
        <div class="flex items-center justify-between mb-12">
            <div>
                <h1 class="text-4xl font-black text-white tracking-tight uppercase italic">Live Listeners</h1>
                <p class="text-gray-500 font-mono text-[10px] uppercase tracking-[0.3em] mt-1">Status: Monitoring Outbound Streams</p>
            </div>
            <button 
                @click="showModal = true"
                class="neural-button-primary uppercase tracking-widest !px-8"
            >
                Initialize Listener
            </button>
        </div>

        <div v-if="webhooks.length === 0" class="glass-panel p-20 text-center border-dashed border-white/10 bg-transparent">
            <div class="text-5xl mb-6 grayscale opacity-20">🪝</div>
            <h3 class="text-lg font-bold text-white uppercase tracking-widest mb-2">No Listeners Configured</h3>
            <p class="text-gray-600 text-xs mb-8 uppercase tracking-tighter">Register an endpoint to receive real-time neural events.</p>
            <button @click="showModal = true" class="text-indigo-400 font-black hover:text-white transition uppercase tracking-widest text-[10px]">
                + Start First Stream
            </button>
        </div>

        <div v-else class="grid gap-8">
            <div v-for="webhook in webhooks" :key="webhook.id" class="neural-card-indigo group !p-0 overflow-hidden">
                <div class="p-8">
                    <div class="flex items-start justify-between gap-12">
                        <div class="flex-1 min-w-0">
                            <div class="flex items-center gap-4 mb-4">
                                <div class="w-2 h-2 rounded-full shadow-[0_0_8px_rgba(16,185,129,0.8)]" :class="webhook.is_active ? 'bg-emerald-500 animate-pulse' : 'bg-rose-500'"></div>
                                <h3 class="text-xl font-black text-white truncate font-mono tracking-tighter">{{ webhook.url }}</h3>
                            </div>
                            
                            <div class="flex flex-wrap gap-2 mb-8">
                                <span v-for="event in webhook.events" :key="event" class="bg-indigo-500/5 text-indigo-300 text-[9px] font-black px-2 py-1 rounded border border-indigo-500/10 uppercase tracking-widest">
                                    {{ event }}
                                </span>
                            </div>

                            <div v-if="webhook.semantic_query" class="mb-8 p-4 bg-black/40 rounded-xl border border-white/5">
                                <span class="text-[9px] text-gray-600 uppercase tracking-[0.2em] font-black block mb-2">Semantic Filter</span>
                                <p class="text-sm text-indigo-200 italic font-medium leading-relaxed">"{{ webhook.semantic_query }}"</p>
                            </div>

                            <div class="mb-8">
                                <span class="text-[9px] text-gray-600 uppercase tracking-[0.2em] font-black block mb-2">Encryption Secret</span>
                                <div class="flex items-center gap-3">
                                    <code class="text-xs font-mono text-gray-500 bg-black/60 px-3 py-2 rounded-lg border border-white/5 min-w-[280px]">
                                        {{ showingSecret === webhook.id ? webhook.secret : 'whsec_••••••••••••••••••••••••••••••••' }}
                                    </code>
                                    <button @click="toggleSecret(webhook.id)" class="text-[9px] text-indigo-400 hover:text-white transition uppercase font-black tracking-widest ml-2">
                                        {{ showingSecret === webhook.id ? 'Hide' : 'Reveal' }}
                                    </button>
                                </div>
                            </div>

                            <div class="flex items-center gap-6 text-[10px] text-gray-600 font-bold uppercase tracking-widest">
                                <span>Initialized {{ new Date(webhook.created_at).toLocaleDateString() }}</span>
                                <div v-if="webhook.failure_count > 0" class="flex items-center gap-2 text-rose-500/80">
                                    <span class="w-1 h-1 rounded-full bg-rose-500"></span>
                                    <span>{{ webhook.failure_count }} Interruptions</span>
                                </div>
                            </div>
                        </div>

                        <div class="shrink-0 flex flex-col gap-3">
                            <button @click="testWebhook(webhook.id)" class="neural-button-secondary !py-2 uppercase !text-[10px] tracking-widest">
                                Ping
                            </button>
                            <button @click="deleteWebhook(webhook.id)" class="neural-button-danger !py-2 uppercase !text-[10px] tracking-widest">
                                Purge
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Add Webhook Modal -->
        <div v-if="showModal" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/90 backdrop-blur-md">
            <div class="glass-panel p-10 max-w-xl w-full border-white/10 shadow-[0_0_50px_rgba(0,0,0,0.5)]">
                <h2 class="text-3xl font-black text-white uppercase tracking-tight mb-8 italic">New Listener</h2>
                
                <form @submit.prevent="createWebhook" class="space-y-8">
                    <div class="space-y-3">
                        <label class="text-[10px] font-bold text-gray-500 uppercase tracking-[0.2em] ml-1">Endpoint Protocol (HTTPS)</label>
                        <input v-model="webhookForm.url" type="url" required class="neural-input" placeholder="https://api.your-agent.io/v1/hooks">
                    </div>

                    <div class="space-y-3">
                        <label class="text-[10px] font-bold text-gray-500 uppercase tracking-[0.2em] ml-1">Subscription Matrix</label>
                        <div class="grid grid-cols-2 gap-4">
                            <label v-for="event in availableEvents" :key="event" class="flex items-center gap-3 p-4 rounded-xl border border-white/5 bg-white/2 cursor-pointer hover:bg-white/5 transition group">
                                <input type="checkbox" :value="event" v-model="webhookForm.events" class="w-4 h-4 rounded border-white/10 bg-black text-indigo-600 focus:ring-indigo-500 focus:ring-offset-black">
                                <span class="text-[10px] text-gray-400 font-mono uppercase group-hover:text-white transition">{{ event }}</span>
                            </label>
                        </div>
                    </div>

                    <div v-if="webhookForm.events.includes('memory.semantic_match')" class="space-y-3 animate-in fade-in slide-in-from-top-4 duration-500">
                        <label class="text-[10px] font-bold text-gray-500 uppercase tracking-[0.2em] ml-1">Semantic Resonance Query</label>
                        <textarea v-model="webhookForm.semantic_query" rows="2" class="neural-input h-24 resize-none" placeholder="What conceptual triggers should activate this listener?"></textarea>
                    </div>

                    <div class="flex items-center justify-end gap-6 pt-6 border-t border-white/5">
                        <button type="button" @click="showModal = false" class="text-gray-500 hover:text-white transition text-[10px] font-black uppercase tracking-widest">Abort</button>
                        <button type="submit" :disabled="webhookForm.processing" class="neural-button-primary !px-10 py-4 uppercase tracking-[0.2em]">
                            {{ webhookForm.processing ? 'Syncing...' : 'Authorize Listener' }}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    </AppLayout>
</template>
