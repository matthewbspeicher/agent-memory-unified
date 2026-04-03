<script setup>
import { Head, Link } from '@inertiajs/vue3';
import AppLayout from '../Layouts/AppLayout.vue';
import { onMounted, ref, watch } from 'vue';
import ForceGraph3D from '3d-force-graph';

const props = defineProps({
    initialData: Object,
});

const graphContainer = ref(null);
let Graph = null;

onMounted(() => {
    Graph = ForceGraph3D()(graphContainer.value)
        .graphData(props.initialData)
        .nodeLabel('summary')
        .nodeAutoColorBy('type')
        .linkDirectionalParticles(2)
        .linkDirectionalParticleSpeed(d => 0.01)
        .backgroundColor('#050505')
        .nodeThreeObject(node => {
            // Future: Custom 3D shapes for different memory types
            return null; 
        });

    // Handle window resize
    window.addEventListener('resize', () => {
        Graph.width(graphContainer.value.offsetWidth);
        Graph.height(graphContainer.value.offsetHeight);
    });
});
</script>

<template>
    <Head title="Neural Mesh Explorer" />
    <AppLayout>
        <div class="h-[70vh] w-full glass-panel overflow-hidden relative border-white/5 bg-black/40">
            <div class="absolute top-6 left-6 z-10">
                <h1 class="text-2xl font-black text-white uppercase italic tracking-tighter">Neural Mesh Explorer</h1>
                <p class="text-[10px] text-gray-500 font-mono uppercase tracking-[0.3em]">Live Semantic Visualization</p>
            </div>

            <div class="absolute bottom-6 right-6 z-10 flex gap-4">
                <div class="flex items-center gap-2">
                    <span class="w-2 h-2 rounded-full bg-indigo-500"></span>
                    <span class="text-[9px] text-gray-400 font-bold uppercase">Memories</span>
                </div>
                <div class="flex items-center gap-2">
                    <span class="w-2 h-2 rounded-full bg-rose-500"></span>
                    <span class="text-[9px] text-gray-400 font-bold uppercase">Agents</span>
                </div>
            </div>

            <div ref="graphContainer" class="w-full h-full"></div>
        </div>

        <div class="mt-12 grid md:grid-cols-3 gap-8">
            <div class="neural-card p-6">
                <h3 class="text-white font-black text-xs uppercase tracking-widest mb-4">Semantic Proximity</h3>
                <p class="text-gray-500 text-[10px] leading-relaxed">Nodes are positioned based on high-dimensional vector embeddings. Closely related concepts will cluster naturally in 3D space.</p>
            </div>
            <div class="neural-card p-6">
                <h3 class="text-white font-black text-xs uppercase tracking-widest mb-4">Compaction Provenance</h3>
                <p class="text-gray-500 text-[10px] leading-relaxed">Lines between nodes represent 'compacted_from' or 'related_to' relationships, visualizing how granular data evolves into dense knowledge.</p>
            </div>
            <div class="neural-card p-6">
                <h3 class="text-white font-black text-xs uppercase tracking-widest mb-4">Real-time Updates</h3>
                <p class="text-gray-500 text-[10px] leading-relaxed">The mesh reflects live inbound memory streams from your active agents and workspace collaborators.</p>
            </div>
        </div>
    </AppLayout>
</template>

<style>
/* 3D Force Graph Labels styling */
.node-label {
    @apply bg-black/80 backdrop-blur-md border border-white/10 px-2 py-1 rounded text-[10px] text-white font-mono;
}
</style>
