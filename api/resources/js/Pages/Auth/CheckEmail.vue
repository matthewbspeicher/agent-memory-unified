<script setup>
import AppLayout from '../../Layouts/AppLayout.vue';

defineProps({
    email: String,
});
</script>

<template>
    <AppLayout>
        <div class="max-w-md mx-auto text-center">
            <div class="mb-6 text-5xl">✉️</div>
            <h1 class="text-3xl font-bold mb-2">Check your email</h1>
            <p class="text-gray-400 mb-6">
                We sent a magic link to
                <span v-if="email" class="text-white font-medium">{{ email }}</span>
                <span v-else>your email</span>.
                Click the link to sign in.
            </p>
            <p class="text-sm text-gray-500">
                Didn't get it? Check your spam folder, or
                <a href="/login" class="text-indigo-400 hover:text-indigo-300">try again</a>.
            </p>
        </div>
    </AppLayout>
</template>
