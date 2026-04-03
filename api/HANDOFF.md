# Handoff Plan — Agent Memory Commons

> If Claude or Gemini picks up this project mid-session, read this first.
> Last updated: 2026-03-10

---

## Project State: User Registration UI — COMPLETE

All phases of the Vue 3 + Inertia + Magic Link auth plan are done:

- [x] Package installs (inertiajs/inertia-laravel, vue@3, @inertiajs/vue3, @vitejs/plugin-vue)
- [x] Inertia scaffolding (app.blade.php, vite.config.js, app.js, HandleInertiaRequests middleware)
- [x] Migration: magic_link_token + magic_link_expires_at on users table
- [x] User model: magic link helpers, agents() relationship, ensureApiToken()
- [x] MagicLinkMail + email template
- [x] MagicLinkController (login, sendLink, checkEmail, verifyLink, logout)
- [x] DashboardController (show, registerAgent)
- [x] Web routes in routes/web.php
- [x] Vue pages: Login.vue, CheckEmail.vue, Dashboard.vue, AppLayout.vue
- [x] 12 feature tests for auth flow (MagicLinkAuthTest.php)
- [x] All 35 tests pass, Vite builds clean

---

## What to Build Next (Priority Order)

### 1. Domain & Deploy (agentmemory.dev)
- User is handling domain purchase
- Deploy to Railway: Postgres + pgvector, set OPENAI_API_KEY
- Set MAIL_MAILER to a real provider (Resend, Postmark, or SES)
- `npm run build` before deploy (assets go to public/build/)

### 2. Dashboard.html SSE Polish
- `public/dashboard.html` has a working real-time SSE feed
- Needs styling to match the new dark theme (bg-gray-950, indigo accents)
- API_BASE is already set to relative URL

### 3. API Documentation Page
- Consider adding a `/docs` route serving an Inertia page
- Document all `/v1/*` endpoints with examples
- Could use the skill.md content as a starting point

### 4. Production Hardening
- Rate limit magic link sends (prevent email spam): throttle sendLink
- Add CSRF protection for magic link forms (already handled by Inertia)
- Consider email verification / confirmation step
- Add password reset alternative flow if needed later

---

## Key File Locations

| What | Where |
|------|-------|
| API routes | `routes/api.php` |
| Web routes | `routes/web.php` |
| Auth controllers | `app/Http/Controllers/Auth/` |
| API controllers | `app/Http/Controllers/Api/` |
| Vue pages | `resources/js/Pages/` |
| Layout | `resources/js/Layouts/AppLayout.vue` |
| Inertia middleware | `app/Http/Middleware/HandleInertiaRequests.php` |
| Agent token middleware | `app/Http/Middleware/AuthenticateAgent.php` |
| Models | `app/Models/User.php`, `Agent.php`, `Memory.php` |
| Services | `app/Services/EmbeddingService.php`, `MemoryService.php` |
| Tests | `tests/Feature/MemoryApiTest.php`, `MagicLinkAuthTest.php` |
| SSE dashboard | `public/dashboard.html` |
| Skill discovery | `public/skill.md` |

## Runner Commands

```bash
# Host tools (not Sail)
php artisan test                    # Run all 35 tests
php artisan test --stop-on-failure  # Debug failures
npx vite build                     # Build frontend assets
php artisan serve                   # Dev server on :8000

# Artisan helpers
php artisan tinker                  # REPL
php artisan owner:create            # Create owner user
php artisan agent:register          # Register agent via CLI
```

## Token Prefixes
- `own_` — owner/user tokens (for registering agents)
- `amc_` — agent tokens (for memory API access)

## Tech Stack
- Laravel 12 / PHP 8.3
- Vue 3 + Inertia.js v2
- PostgreSQL + pgvector
- Tailwind CSS v4
- Vite 7
- Pest testing framework
