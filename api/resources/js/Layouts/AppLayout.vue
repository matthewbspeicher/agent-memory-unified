<script setup>
import { Link, usePage } from '@inertiajs/vue3';
import { computed } from 'vue';

const page = usePage();
const user = computed(() => page.props.auth.user);
</script>

<template>
    <div class="min-h-screen relative flex flex-col">
        <!-- Floating Navigation -->
        <nav class="sticky top-4 mx-auto w-[calc(100%-2rem)] max-w-5xl z-50">
            <div class="glass-panel px-6 py-3 flex items-center justify-between border-white/10">
                <Link href="/" class="text-xl font-black tracking-tighter neural-text-gradient">
                    REMEMBR
                </Link>

                <!-- Auth Navigation -->
                <div v-if="user" class="flex items-center gap-6">
                    <Link href="/dashboard" class="text-xs font-bold text-gray-400 hover:text-white transition uppercase tracking-widest">Agents</Link>
                    <Link href="/explorer" class="text-xs font-bold text-gray-400 hover:text-white transition uppercase tracking-widest">Explorer</Link>
                    <Link href="/dashboard/webhooks" class="text-xs font-bold text-gray-400 hover:text-white transition uppercase tracking-widest">Webhooks</Link>
                    <Link href="/arena" class="text-xs font-bold text-gray-400 hover:text-white transition uppercase tracking-widest">Arena</Link>
                    <Link href="/commons" class="text-xs font-bold text-gray-400 hover:text-white transition uppercase tracking-widest">Commons</Link>

                    <div class="h-4 w-px bg-white/10 mx-2"></div>

                    <span class="text-[10px] font-mono text-gray-600 uppercase tracking-widest">{{ user.email }}</span>

                    <Link href="/logout" method="post" as="button" class="text-xs font-bold text-gray-500 hover:text-rose-400 transition uppercase tracking-widest ml-4">
                        Exit
                    </Link>
                </div>

                <!-- Guest Navigation -->
                <div v-else class="flex items-center gap-6">
                    <Link href="/arena" class="text-xs font-bold text-gray-400 hover:text-white transition uppercase tracking-widest">Arena</Link>
                    <Link href="/docs" class="text-xs font-bold text-gray-400 hover:text-white transition uppercase tracking-widest">Docs</Link>
                    <Link href="/login" class="neural-button-primary !px-4 !py-1.5 !text-[10px] uppercase tracking-widest">
                        Sign In
                    </Link>
                </div>
            </div>
        </nav>

        <!-- Main Content -->
        <main class="flex-1 max-w-5xl w-full mx-auto px-6 py-12 relative z-10">
            <slot />
        </main>

        <!-- Footer -->
        <footer class="max-w-5xl w-full mx-auto px-6 py-8 border-t border-white/5 text-center">
            <p class="text-[10px] font-mono text-gray-600 uppercase tracking-[0.2em]">
                &copy; 2026 Remembr.dev // Neural Mesh Protocol v1.4
            </p>
        </footer>
    </div>
</template>
