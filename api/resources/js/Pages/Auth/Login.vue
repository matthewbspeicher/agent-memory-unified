<script setup>
import { useForm, usePage } from '@inertiajs/vue3';
import AppLayout from '../../Layouts/AppLayout.vue';
import { computed } from 'vue';

const page = usePage();
const flash = computed(() => page.props.flash?.message);

const form = useForm({
    name: '',
    email: '',
});

function submit() {
    form.post('/login');
}
</script>

<template>
    <AppLayout>
        <div class="max-w-md mx-auto">
            <h1 class="text-3xl font-bold mb-2">Sign in</h1>
            <p class="text-gray-400 mb-8">
                Enter your name and email. We'll send you a magic link — no password needed.
            </p>

            <div v-if="flash" class="mb-6 rounded-lg bg-amber-900/30 border border-amber-700/50 px-4 py-3 text-amber-200 text-sm">
                {{ flash }}
            </div>

            <form @submit.prevent="submit" class="space-y-5">
                <div>
                    <label for="name" class="block text-sm font-medium text-gray-300 mb-1">Name</label>
                    <input
                        id="name"
                        v-model="form.name"
                        type="text"
                        required
                        autofocus
                        class="w-full rounded-lg border border-gray-700 bg-gray-800 px-4 py-2.5 text-white placeholder-gray-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 outline-none"
                        placeholder="Your name"
                    />
                    <p v-if="form.errors.name" class="mt-1 text-sm text-red-400">{{ form.errors.name }}</p>
                </div>

                <div>
                    <label for="email" class="block text-sm font-medium text-gray-300 mb-1">Email</label>
                    <input
                        id="email"
                        v-model="form.email"
                        type="email"
                        required
                        class="w-full rounded-lg border border-gray-700 bg-gray-800 px-4 py-2.5 text-white placeholder-gray-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 outline-none"
                        placeholder="you@example.com"
                    />
                    <p v-if="form.errors.email" class="mt-1 text-sm text-red-400">{{ form.errors.email }}</p>
                </div>

                <button
                    type="submit"
                    :disabled="form.processing"
                    class="w-full rounded-lg bg-indigo-600 px-4 py-2.5 font-medium text-white hover:bg-indigo-500 disabled:opacity-50 transition"
                >
                    {{ form.processing ? 'Sending...' : 'Send magic link' }}
                </button>
            </form>
        </div>
    </AppLayout>
</template>
