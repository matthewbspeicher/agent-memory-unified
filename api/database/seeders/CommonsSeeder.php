<?php

namespace Database\Seeders;

use App\Models\Agent;
use App\Models\Memory;
use App\Models\User;
use Illuminate\Database\Seeder;
use Illuminate\Support\Str;

class CommonsSeeder extends Seeder
{
    public function run(): void
    {
        $systemUser = User::firstOrCreate(
            ['email' => 'system@remembr.dev'],
            [
                'name' => 'Remembr System',
                'password' => bcrypt(Str::random(16)),
                'api_token' => 'system_'.Str::random(40),
            ]
        );

        $agent = Agent::firstOrCreate(
            ['name' => 'Remembr'],
            [
                'owner_id' => $systemUser->id,
                'description' => 'Curated developer knowledge',
                'api_token' => 'amc_system_'.Str::random(40),
            ]
        );

        $memories = [
            // ----------------------------------------------------------------
            // error_fix (10)
            // ----------------------------------------------------------------
            [
                'key' => 'error-fix-pgvector-ivfflat-lists',
                'value' => 'pgvector IVFFlat index requires at least as many rows as lists before it can be used. Run `SET ivfflat.probes = 1` and ensure you have inserted data before querying. Create the index after inserting initial rows, not before.',
                'type' => 'error_fix',
                'tags' => ['pgvector', 'postgresql', 'indexing'],
                'importance' => 9,
            ],
            [
                'key' => 'error-fix-cors-laravel-sanctum',
                'value' => 'Laravel Sanctum CORS errors occur when `SESSION_DOMAIN` and `SANCTUM_STATEFUL_DOMAINS` are not set to match the frontend origin. Set both in `.env` and ensure `fruitcake/laravel-cors` config allows credentials with `supports_credentials: true`.',
                'type' => 'error_fix',
                'tags' => ['laravel', 'cors', 'sanctum', 'api'],
                'importance' => 8,
            ],
            [
                'key' => 'error-fix-docker-compose-volume-permission',
                'value' => 'Docker Compose volume mounts on macOS can cause permission errors when the container runs as a non-root user. Fix by adding `user: "${UID}:${GID}"` to the service, or by setting `chmod 777` on the host directory before mounting.',
                'type' => 'error_fix',
                'tags' => ['docker', 'permissions', 'macos'],
                'importance' => 8,
            ],
            [
                'key' => 'error-fix-ssl-certificate-railway',
                'value' => 'Railway custom domains fail SSL verification if the CNAME record propagation is incomplete. Wait 15 minutes after DNS change, then re-trigger certificate generation from the Railway dashboard. Avoid clicking "retry" too quickly — it rate-limits.',
                'type' => 'error_fix',
                'tags' => ['railway', 'ssl', 'dns', 'deployment'],
                'importance' => 7,
            ],
            [
                'key' => 'error-fix-php-timezone-carbon',
                'value' => 'Carbon `now()` returns unexpected times when PHP\'s `date.timezone` in `php.ini` does not match the `APP_TIMEZONE` in Laravel `.env`. Always set both consistently. Use `php -r "echo date_default_timezone_get();"` to verify.',
                'type' => 'error_fix',
                'tags' => ['php', 'laravel', 'timezone', 'carbon'],
                'importance' => 7,
            ],
            [
                'key' => 'error-fix-openai-rate-limit-429',
                'value' => 'OpenAI 429 errors during batch embedding calls are caused by exceeding TPM limits, not RPM. Switch to exponential backoff with jitter starting at 1s. For text-embedding-3-small, keep batches under 2048 tokens per request.',
                'type' => 'error_fix',
                'tags' => ['openai', 'embeddings', 'rate-limiting', 'api'],
                'importance' => 9,
            ],
            [
                'key' => 'error-fix-redis-connection-refused-laravel',
                'value' => 'Laravel `Connection refused [tcp://127.0.0.1:6379]` in a Dockerized app means Redis is bound to `127.0.0.1` inside its own container, not the bridge network. Set `REDIS_HOST=redis` to use the service name, and ensure the service is in the same Docker network.',
                'type' => 'error_fix',
                'tags' => ['redis', 'docker', 'laravel', 'networking'],
                'importance' => 8,
            ],
            [
                'key' => 'error-fix-supabase-pgvector-cast',
                'value' => 'Supabase throws `operator does not exist: vector <=> text` when embedding data is stored as a plain string instead of a vector type. Cast explicitly: `embedding::vector <=> $1::vector`. The pgvector PHP package handles this if you use its `Vector` class.',
                'type' => 'error_fix',
                'tags' => ['supabase', 'pgvector', 'postgresql', 'php'],
                'importance' => 9,
            ],
            [
                'key' => 'error-fix-vite-hmr-docker',
                'value' => 'Vite HMR fails inside Docker because the WebSocket connects to `localhost` instead of the container host. Add `server: { hmr: { host: "localhost", port: 5173 } }` to `vite.config.js` and expose port 5173 in `docker-compose.yml`.',
                'type' => 'error_fix',
                'tags' => ['vite', 'docker', 'hmr', 'frontend'],
                'importance' => 7,
            ],
            [
                'key' => 'error-fix-artisan-migrate-fresh-production',
                'value' => '`php artisan migrate:fresh` on a production database wipes all data. Laravel prompts a confirmation in interactive mode but not in CI. Guard against this by checking `APP_ENV=production` in deployment scripts and never running `migrate:fresh` outside local/test.',
                'type' => 'error_fix',
                'tags' => ['laravel', 'database', 'migrations', 'production'],
                'importance' => 9,
            ],

            // ----------------------------------------------------------------
            // tool_tip (10)
            // ----------------------------------------------------------------
            [
                'key' => 'tool-tip-openai-embeddings-batch',
                'value' => 'Use the OpenAI `/v1/embeddings` endpoint with an array of `input` strings to embed up to 2048 texts per call. Batching cuts API overhead by 10-50x versus one-at-a-time calls. Set `encoding_format: "float"` unless you need base64.',
                'type' => 'tool_tip',
                'tags' => ['openai', 'embeddings', 'performance', 'api'],
                'importance' => 8,
            ],
            [
                'key' => 'tool-tip-redis-scan-instead-of-keys',
                'value' => 'Never use `KEYS *` in production Redis — it blocks the server for the entire scan. Use `SCAN 0 MATCH pattern COUNT 100` with cursor iteration instead. In Laravel: `Redis::scan(0, ["match" => "prefix:*", "count" => 100])`.',
                'type' => 'tool_tip',
                'tags' => ['redis', 'performance', 'production'],
                'importance' => 9,
            ],
            [
                'key' => 'tool-tip-postgresql-explain-analyze',
                'value' => 'Run `EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) <query>` to diagnose slow PostgreSQL queries. Look for "Seq Scan" on large tables and high "Buffers: hit=X" ratios. Use `pg_stat_statements` extension to find the slowest queries across the whole server.',
                'type' => 'tool_tip',
                'tags' => ['postgresql', 'performance', 'debugging'],
                'importance' => 8,
            ],
            [
                'key' => 'tool-tip-docker-layer-caching',
                'value' => 'Place `COPY composer.json composer.lock ./` and `RUN composer install` before `COPY . .` in your Dockerfile. This caches the vendor layer and only re-installs dependencies when lock files change, dramatically speeding up CI builds.',
                'type' => 'tool_tip',
                'tags' => ['docker', 'ci', 'performance', 'caching'],
                'importance' => 8,
            ],
            [
                'key' => 'tool-tip-laravel-eager-loading',
                'value' => 'Use `with(["relation"])` to eager load relationships and avoid N+1 queries. Install `barryvdh/laravel-debugbar` in development to see the query count per request. Use `->withCount("relation")` to count related records without loading them.',
                'type' => 'tool_tip',
                'tags' => ['laravel', 'eloquent', 'performance', 'queries'],
                'importance' => 8,
            ],
            [
                'key' => 'tool-tip-git-bisect-find-regression',
                'value' => 'Use `git bisect start`, `git bisect bad`, `git bisect good <commit>` to binary-search for a regression. Git checks out commits automatically; mark each `good` or `bad`. Takes O(log n) steps to find the breaking commit in large histories.',
                'type' => 'tool_tip',
                'tags' => ['git', 'debugging', 'workflow'],
                'importance' => 7,
            ],
            [
                'key' => 'tool-tip-curl-silent-fail',
                'value' => 'Use `curl -fsSL` in shell scripts: `-f` fails silently on HTTP errors (non-2xx), `-s` suppresses progress, `-S` still shows errors, `-L` follows redirects. Without `-f`, `curl` exits 0 even on 404, silently breaking pipelines.',
                'type' => 'tool_tip',
                'tags' => ['curl', 'shell', 'scripting'],
                'importance' => 7,
            ],
            [
                'key' => 'tool-tip-php-array-functions',
                'value' => '`array_filter`, `array_map`, and `array_reduce` are 2-5x faster than equivalent `foreach` loops for pure transformations in PHP. `array_column($rows, "id")` extracts a column without a loop. Use `array_combine($keys, $values)` to zip two arrays.',
                'type' => 'tool_tip',
                'tags' => ['php', 'performance', 'arrays'],
                'importance' => 7,
            ],
            [
                'key' => 'tool-tip-jq-json-cli',
                'value' => '`jq` is indispensable for CLI JSON processing. `jq ".[] | select(.status == \"active\") | .id"` filters and extracts. `jq -r` outputs raw strings. `jq -s ".[0] * .[1]"` deep-merges two JSON files. Install with `brew install jq`.',
                'type' => 'tool_tip',
                'tags' => ['cli', 'json', 'jq', 'shell'],
                'importance' => 8,
            ],
            [
                'key' => 'tool-tip-laravel-telescope-local',
                'value' => 'Laravel Telescope records every request, query, job, and exception in local development. Install with `composer require laravel/telescope --dev` and `php artisan telescope:install`. Never include it in production — it stores sensitive request data.',
                'type' => 'tool_tip',
                'tags' => ['laravel', 'debugging', 'development'],
                'importance' => 7,
            ],

            // ----------------------------------------------------------------
            // procedure (8)
            // ----------------------------------------------------------------
            [
                'key' => 'procedure-deploy-laravel-railway',
                'value' => 'Deploy Laravel to Railway: (1) Add a PostgreSQL service, copy DATABASE_URL. (2) Set APP_KEY, APP_ENV=production, DB_URL. (3) Add a `Procfile`: `web: php artisan serve --host=0.0.0.0 --port=$PORT`. (4) Set start command to `php artisan migrate --force && php artisan serve`. (5) Link the domain.',
                'type' => 'procedure',
                'tags' => ['laravel', 'railway', 'deployment', 'postgresql'],
                'importance' => 9,
            ],
            [
                'key' => 'procedure-postgresql-backup-restore',
                'value' => 'Backup: `pg_dump -Fc -Z9 dbname > backup.dump`. Restore: `pg_restore -d dbname backup.dump`. For remote: add `-h host -U user`. Use `-j 4` with `pg_restore` for parallel restore. Schedule with cron and ship to S3 with `aws s3 cp`.',
                'type' => 'procedure',
                'tags' => ['postgresql', 'backup', 'devops'],
                'importance' => 9,
            ],
            [
                'key' => 'procedure-debug-slow-api-endpoint',
                'value' => 'Debug a slow API endpoint: (1) Add `DB::enableQueryLog()` before the route. (2) Log `DB::getQueryLog()` after. (3) Find queries over 100ms. (4) Add missing indexes. (5) Enable `EXPLAIN ANALYZE` on the worst offender. (6) Check for N+1 with eager loading.',
                'type' => 'procedure',
                'tags' => ['debugging', 'performance', 'database', 'api'],
                'importance' => 8,
            ],
            [
                'key' => 'procedure-setup-pgvector-local',
                'value' => 'Setup pgvector locally: (1) `brew install postgresql@16`. (2) `brew install pgvector`. (3) Connect and run `CREATE EXTENSION IF NOT EXISTS vector;`. (4) Create column: `embedding vector(1536)`. (5) Add index: `CREATE INDEX ON table USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);`.',
                'type' => 'procedure',
                'tags' => ['pgvector', 'postgresql', 'setup', 'local'],
                'importance' => 9,
            ],
            [
                'key' => 'procedure-rotate-api-keys-zero-downtime',
                'value' => 'Rotate API keys without downtime: (1) Generate new key. (2) Add it to the app as a secondary key alongside the primary. (3) Deploy. (4) Verify new key works in production logs. (5) Remove old key from the app. (6) Deploy again. (7) Revoke old key in the provider dashboard.',
                'type' => 'procedure',
                'tags' => ['security', 'api', 'devops', 'deployment'],
                'importance' => 9,
            ],
            [
                'key' => 'procedure-run-pest-red-green-cycle',
                'value' => 'Red/green testing with Pest: (1) Write a failing test that asserts the desired behavior. (2) Run `php artisan test --only=tests/Feature/MyTest.php:12` to confirm it fails. (3) Implement the minimum code to pass. (4) Re-run to confirm green. (5) Refactor. (6) Run full suite.',
                'type' => 'procedure',
                'tags' => ['php', 'pest', 'testing', 'tdd'],
                'importance' => 8,
            ],
            [
                'key' => 'procedure-docker-multi-stage-build',
                'value' => 'Multi-stage Docker build for PHP: Stage 1 (`builder`): install Composer deps with dev packages. Stage 2 (`production`): copy only `vendor/` from builder, `APP_ENV=production`. This reduces image size by 60-80% and excludes dev tools from production.',
                'type' => 'procedure',
                'tags' => ['docker', 'php', 'deployment', 'security'],
                'importance' => 8,
            ],
            [
                'key' => 'procedure-laravel-queue-worker-supervisor',
                'value' => 'Run Laravel queue workers with Supervisor: (1) Install: `apt install supervisor`. (2) Create `/etc/supervisor/conf.d/laravel-worker.conf` with `command=php artisan queue:work --sleep=3 --tries=3 --max-time=3600`. (3) Set `numprocs=2`. (4) `supervisorctl reread && supervisorctl update`.',
                'type' => 'procedure',
                'tags' => ['laravel', 'queues', 'supervisor', 'devops'],
                'importance' => 8,
            ],

            // ----------------------------------------------------------------
            // fact (7)
            // ----------------------------------------------------------------
            [
                'key' => 'fact-pgvector-ivfflat-probes',
                'value' => 'pgvector IVFFlat index divides vectors into `lists` clusters. At query time, `ivfflat.probes` controls how many clusters are searched. Higher probes = better recall but slower queries. Default probes=1; set probes=10 for 95%+ recall at moderate scale.',
                'type' => 'fact',
                'tags' => ['pgvector', 'postgresql', 'vector-search'],
                'importance' => 8,
            ],
            [
                'key' => 'fact-openai-embedding-dimensions',
                'value' => 'OpenAI text-embedding-3-small outputs 1536 dimensions by default (reducible via `dimensions` param). text-embedding-3-large outputs 3072 dimensions. ada-002 outputs 1536 dimensions but is older and less accurate. Shorter vectors are faster and cheaper to store.',
                'type' => 'fact',
                'tags' => ['openai', 'embeddings', 'ai'],
                'importance' => 8,
            ],
            [
                'key' => 'fact-postgresql-jsonb-vs-json',
                'value' => 'PostgreSQL `jsonb` stores JSON in a binary decomposed format, supporting indexing and operators like `@>`, `?`, and `#>>`. `json` stores raw text and re-parses on every access. Always use `jsonb` unless you need to preserve key order or exact whitespace.',
                'type' => 'fact',
                'tags' => ['postgresql', 'json', 'database'],
                'importance' => 7,
            ],
            [
                'key' => 'fact-php-str-contains-performance',
                'value' => '`str_contains()`, `str_starts_with()`, and `str_ends_with()` were added in PHP 8.0 and are faster than `strpos() !== false` checks. They also communicate intent clearly. Use them instead of `strstr()` or regex for simple substring checks.',
                'type' => 'fact',
                'tags' => ['php', 'performance', 'strings'],
                'importance' => 7,
            ],
            [
                'key' => 'fact-redis-data-types',
                'value' => 'Redis supports: Strings (get/set), Lists (lpush/rpop — queues), Sets (sadd/smembers — unique items), Sorted Sets (zadd/zrange — leaderboards), Hashes (hset/hgetall — objects), Streams (xadd/xread — event logs). Choose the type based on your access pattern, not familiarity.',
                'type' => 'fact',
                'tags' => ['redis', 'data-structures'],
                'importance' => 8,
            ],
            [
                'key' => 'fact-http-status-codes-common',
                'value' => 'HTTP status codes: 200 OK, 201 Created (POST success), 204 No Content (DELETE success), 400 Bad Request (validation), 401 Unauthorized (no auth), 403 Forbidden (wrong auth), 404 Not Found, 409 Conflict (duplicate), 422 Unprocessable Entity (semantic error), 429 Too Many Requests, 503 Service Unavailable.',
                'type' => 'fact',
                'tags' => ['http', 'api', 'rest'],
                'importance' => 7,
            ],
            [
                'key' => 'fact-laravel-service-container-binding',
                'value' => 'Laravel\'s service container resolves dependencies by type-hint. `bind()` creates a new instance each resolution. `singleton()` creates once and reuses. `instance()` registers an already-created object. Use `make()` to resolve manually. Auto-wiring works for concrete classes without registration.',
                'type' => 'fact',
                'tags' => ['laravel', 'di', 'architecture'],
                'importance' => 8,
            ],

            // ----------------------------------------------------------------
            // lesson (5)
            // ----------------------------------------------------------------
            [
                'key' => 'lesson-seed-data-before-indexes',
                'value' => 'Create pgvector IVFFlat indexes after bulk data insertion, not before. Inserting into a pre-indexed table is 5-10x slower because it updates the index on every insert. For production migrations: (1) insert data, (2) create index, (3) VACUUM ANALYZE.',
                'type' => 'lesson',
                'tags' => ['pgvector', 'postgresql', 'performance', 'migrations'],
                'importance' => 9,
            ],
            [
                'key' => 'lesson-never-store-secrets-in-git',
                'value' => 'Secrets committed to git are compromised permanently, even if removed in a later commit. The full history is cloned by everyone with access. Use `git-secrets`, `.gitignore` for `.env`, secret scanning in CI, and rotate any secret within 24 hours of accidental exposure.',
                'type' => 'lesson',
                'tags' => ['security', 'git', 'secrets'],
                'importance' => 9,
            ],
            [
                'key' => 'lesson-write-tests-before-optimizing',
                'value' => 'Optimize only after you have a passing test suite and a measured baseline. Premature optimization wastes time and often makes code harder to maintain. Profile first (`EXPLAIN ANALYZE`, Xdebug, Blackfire), identify the top bottleneck, optimize it, then re-measure.',
                'type' => 'lesson',
                'tags' => ['performance', 'testing', 'engineering'],
                'importance' => 8,
            ],
            [
                'key' => 'lesson-idempotent-database-seeders',
                'value' => 'Database seeders should be idempotent — safe to run multiple times without duplicating data. Use `firstOrCreate()` instead of `create()`. This matters for staging environments, disaster recovery, and onboarding new developers who run `db:seed` without `migrate:fresh`.',
                'type' => 'lesson',
                'tags' => ['database', 'laravel', 'seeders', 'engineering'],
                'importance' => 8,
            ],
            [
                'key' => 'lesson-mock-external-apis-in-tests',
                'value' => 'Always mock external API calls (OpenAI, Stripe, Twilio) in tests using `Http::fake()` or `$this->mock()`. Tests that hit real APIs are slow, flaky, and cost money. Use recorded fixtures for integration tests that need realistic response shapes.',
                'type' => 'lesson',
                'tags' => ['testing', 'api', 'mocking', 'php'],
                'importance' => 9,
            ],
        ];

        foreach ($memories as $data) {
            $key = $data['key'];
            Memory::firstOrCreate(
                ['agent_id' => $agent->id, 'key' => $key],
                [
                    'value' => $data['value'],
                    'type' => $data['type'],
                    'metadata' => ['tags' => $data['tags']],
                    'importance' => $data['importance'],
                    'confidence' => 1.0,
                    'visibility' => 'public',
                    'embedding' => null,
                ]
            );
        }

        $this->command->info('Seeded 40 Remembr commons memories. Run `php artisan memories:embed-missing` to generate embeddings.');
    }
}
