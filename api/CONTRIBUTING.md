# Contributing to Remembr.dev

Thanks for your interest in contributing!

## Prerequisites

- PHP 8.3+
- PostgreSQL 15+ with [pgvector](https://github.com/pgvector/pgvector)
- Composer 2.x
- Node.js 18+ (for the MCP server and frontend assets)

## Local Setup

1. Fork and clone the repository:
```bash
git clone https://github.com/YOUR_USERNAME/remembr-dev.git
cd remembr-dev
```

2. Install dependencies:
```bash
composer install && npm install
```

3. Configure environment and database:
```bash
cp .env.example .env
php artisan key:generate
createdb agent_memory
# Edit .env with your database credentials
php artisan migrate
```

4. Start the development server:
```bash
php artisan serve
```

## Running Tests

```bash
php artisan test
```

Run a specific test file:
```bash
php artisan test tests/Feature/MemoryApiTest.php
```

## Code Style

- PSR-12 coding style
- Type hints and return types on all methods
- Follow standard Laravel conventions

## Submitting a Pull Request

1. Create a feature branch from `main`:
```bash
git checkout -b feature/your-feature-name
```
2. Make your changes and write tests for new functionality.
3. Ensure all tests pass: `php artisan test`
4. Commit with a clear, descriptive message.
5. Push to your fork and open a pull request against `main`.
6. Describe what your PR does and link any related issues.

## Reporting Bugs

Use the [GitHub issue tracker](https://github.com/matthewbspeicher/remembr-dev/issues) with steps to reproduce, expected behavior, and actual behavior.

## Questions?

Open a discussion on GitHub or ask in our [Discord](https://discord.gg/RemembrDev).
