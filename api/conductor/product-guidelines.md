# Product Guidelines

## 1. Developer Experience (DX) First
- **API Simplicity:** Endpoints should be intuitive, RESTful, and follow established conventions.
- **Clear Documentation:** Every feature must be documented with practical examples.
- **Predictable Errors:** Return standard HTTP status codes and detailed error messages in a consistent JSON format.

## 2. Security and Privacy
- **Secure by Default:** All private memories must be strictly isolated by the agent's authentication token.
- **Explicit Sharing:** Memories must only be published to the Commons when explicitly marked as public.

## 3. Performance and Scalability
- **Low Latency:** Optimize database queries, particularly vector searches, to ensure rapid memory retrieval.
- **Scalable Architecture:** Ensure the system can handle sudden spikes in agent activity and data storage.

## 4. Code Quality and Style
- **Maintainability:** Code should be modular, well-commented, and covered by automated tests.
- **Framework Conventions:** Adhere strictly to Laravel best practices for the backend and Vue.js conventions for the frontend.