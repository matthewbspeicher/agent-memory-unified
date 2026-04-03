import { AgentMemoryClient } from '@remembr/sdk';

// Initialize the client using the REMEMBR_AGENT_TOKEN environment variable
const client = new AgentMemoryClient(process.env.REMEMBR_AGENT_TOKEN);

async function main() {
    // Store a memory
    const memory = await client.store({
        value: "The user prefers TypeScript for frontend work.",
        key: "user_preference_ts",
        tags: ["frontend", "user-preference"],
        ttl: "30d"
    });
    console.log(`Stored memory ID: ${memory.id}`);

    // Retrieve a memory by key
    const fetched = await client.get('user_preference_ts');
    console.log(`Fetched memory: ${fetched.value}`);

    // Search your memories semantically
    const results = await client.search("What language does the user like for UI?", { limit: 2 });
    console.log("Search results:");
    for (const r of results) {
        console.log(`- ${r.value} (Score: ${r.similarity})`);
    }
}

main().catch(console.error);
