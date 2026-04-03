# Tech Stack

## Backend
- **Language:** PHP 8.x
- **Framework:** Laravel (using Octane and FrankenPHP for high-performance request handling)

## Frontend
- **Framework:** Vue 3
- **Architecture:** Inertia.js (monolith architecture with SPA feel)
- **Styling:** Tailwind CSS
- **Build Tool:** Vite

## Infrastructure & Data
- **Database:** PostgreSQL (with `pgvector` extension for semantic search capabilities)
- **Search:** Hybrid Search (pgvector cosine similarity + PostgreSQL GIN full-text search with Reciprocal Rank Fusion)
- **Embeddings API:** Gemini (`gemini-embedding-001`)
- **Cache & Sessions:** Redis
- **Email Service:** Resend
- **Deployment:** Railway