<script setup>
import { useForm, usePage, router } from '@inertiajs/vue3';
import AppLayout from '../Layouts/AppLayout.vue';
import { ref, computed } from 'vue';

const props = defineProps({
    workspace: Object,
});

const page = usePage();
const flashSuccess = computed(() => page.props.flash?.success);
const flashError = computed(() => page.props.flash?.error);

const copied = ref(false);
function copyToken(token) {
    if (!token) return;
    navigator.clipboard.writeText(token);
    copied.value = true;
    setTimeout(() => (copied.value = false), 2000);
}

const inviteForm = useForm({
    email: '',
});

function inviteUser() {
    inviteForm.post(`/workspaces/${props.workspace.id}/invite`, {
        preserveScroll: true,
        onSuccess: () => inviteForm.reset(),
    });
}

function removeUser(userId) {
    if (confirm('Are you sure you want to remove this user from the workspace?')) {
        router.delete(`/workspaces/${props.workspace.id}/users/${userId}`, {
            preserveScroll: true,
        });
    }
}

function rotateToken() {
    if (confirm('Are you sure you want to rotate the Workspace API token? The old token will be immediately invalidated.')) {
        router.post(`/workspaces/${props.workspace.id}/token/rotate`, {}, {
            preserveScroll: true,
        });
    }
}
</script>

<template>
    <AppLayout>
        <div class="mb-6 flex items-center justify-between">
            <h1 class="text-3xl font-bold">{{ workspace.name }} Settings</h1>
            <a href="/dashboard" class="text-sm font-medium text-indigo-400 hover:text-indigo-300">
                &larr; Back to Dashboard
            </a>
        </div>

        <div v-if="flashSuccess" class="mb-6 rounded-lg bg-emerald-900/30 border border-emerald-700/50 px-4 py-3 text-emerald-200 text-sm">
            {{ flashSuccess }}
        </div>
        <div v-if="flashError" class="mb-6 rounded-lg bg-red-900/30 border border-red-700/50 px-4 py-3 text-red-200 text-sm">
            {{ flashError }}
        </div>

        <!-- Workspace API Token -->
        <section class="mb-10">
            <h2 class="text-lg font-semibold mb-3 text-gray-200">Workspace API Token</h2>
            <div class="flex items-center gap-3 rounded-lg border border-gray-700 bg-gray-800 px-4 py-3">
                <code class="flex-1 text-sm text-indigo-300 font-mono break-all">{{ workspace.api_token || 'No token generated yet.' }}</code>
                <button
                    v-if="workspace.api_token"
                    @click="copyToken(workspace.api_token)"
                    class="shrink-0 rounded bg-gray-700 px-3 py-1.5 text-xs font-medium text-gray-200 hover:bg-gray-600 transition"
                >
                    {{ copied ? 'Copied!' : 'Copy' }}
                </button>
                <button
                    @click="rotateToken"
                    class="shrink-0 rounded border border-gray-600 px-3 py-1.5 text-xs font-medium text-gray-300 hover:text-white hover:bg-gray-700 transition"
                >
                    Rotate Token
                </button>
            </div>
            <p class="mt-2 text-xs text-gray-500">This token allows you to push/read memories for the entire workspace without passing individual Agent tokens. Use it as a Bearer token: <code>Authorization: Bearer wks_...</code></p>
        </section>

        <!-- Invite User -->
        <section class="mb-10">
            <h2 class="text-lg font-semibold mb-3 text-gray-200">Invite Team Member</h2>
            <form @submit.prevent="inviteUser" class="flex items-end gap-3">
                <div class="flex-1">
                    <label for="invite-email" class="block text-sm font-medium text-gray-300 mb-1">User Email</label>
                    <input
                        id="invite-email"
                        v-model="inviteForm.email"
                        type="email"
                        required
                        class="w-full rounded-lg border border-gray-700 bg-gray-800 px-4 py-2.5 text-white placeholder-gray-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 outline-none"
                        placeholder="colleague@example.com"
                    />
                    <p v-if="inviteForm.errors.email" class="mt-1 text-sm text-red-400">{{ inviteForm.errors.email }}</p>
                </div>
                <button
                    type="submit"
                    :disabled="inviteForm.processing"
                    class="h-[46px] rounded-lg bg-indigo-600 px-5 font-medium text-white hover:bg-indigo-500 disabled:opacity-50 transition"
                >
                    {{ inviteForm.processing ? 'Inviting...' : 'Invite' }}
                </button>
            </form>
            <p class="mt-2 text-xs text-gray-500">The user must already have an account on this platform.</p>
        </section>

        <!-- Members List -->
        <section>
            <h2 class="text-lg font-semibold mb-3 text-gray-200">Workspace Members</h2>
            <div v-if="workspace.users && workspace.users.length === 0" class="text-gray-500 text-sm">
                No members invited yet.
            </div>
            <div v-else class="space-y-3">
                <div
                    v-for="user in workspace.users"
                    :key="user.id"
                    class="rounded-lg border border-gray-700 bg-gray-800/50 px-4 py-3 flex items-center justify-between"
                >
                    <div class="flex flex-col">
                        <span class="font-medium text-white">{{ user.name }} <span v-if="user.id === workspace.owner_id" class="text-xs text-amber-500 ml-2">(Owner)</span></span>
                        <span class="text-sm text-gray-400">{{ user.email }}</span>
                    </div>
                    <div class="flex items-center gap-2">
                        <button
                            v-if="user.id !== workspace.owner_id"
                            @click="removeUser(user.id)"
                            class="rounded bg-gray-700 px-3 py-1.5 text-xs font-medium text-red-400 hover:text-red-300 hover:bg-gray-600 transition"
                        >
                            Remove
                        </button>
                    </div>
                </div>
            </div>
        </section>

    </AppLayout>
</template>
