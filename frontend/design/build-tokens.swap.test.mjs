// frontend/design/build-tokens.swap.test.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { mkdtemp, rm, readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { buildTokens } from './build-tokens.mjs';

const __dirname = dirname(fileURLToPath(import.meta.url));
const MINIMAL = resolve(__dirname, 'fixtures/minimal-valid.md');
const ALL_RED = resolve(__dirname, 'fixtures/all-red.md');

test('swap: red fixture produces only red hex values; none of minimal survive', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'dt-swap-'));
  try {
    const cssPath = join(dir, 'tokens.generated.css');
    const jsPath  = join(dir, 'tailwind.tokens.generated.js');

    // 1. Build with minimal (baseline)
    await buildTokens({ source: MINIMAL, cssOut: cssPath, jsOut: jsPath });
    const cssBefore = await readFile(cssPath, 'utf8');
    // Sanity: minimal's distinctive indigo is present
    assert.match(cssBefore, /#6366F1/);

    // 2. Rebuild with all-red — same paths, overwrites
    await buildTokens({ source: ALL_RED, cssOut: cssPath, jsOut: jsPath });
    const cssAfter = await readFile(cssPath, 'utf8');

    // 3. All red hex values present
    for (const hex of ['#1A0000','#7A0000','#AA0000','#FC0000']) {
      assert.ok(cssAfter.includes(hex), `expected ${hex} in generated CSS`);
    }

    // 4. NONE of the minimal fixture's distinctive colors remain
    assert.equal(cssAfter.includes('#6366F1'), false, 'indigo must be gone');
    assert.equal(cssAfter.includes('#F43F5E'), false, 'rose must be gone');
    assert.equal(cssAfter.includes('#10B981'), false, 'emerald must be gone');

    // 5. Semantic token names are structurally identical — same set of CSS variables
    const varsBefore = [...cssBefore.matchAll(/--color-[a-z0-9-]+(?:-rgb)?:/g)].map((m) => m[0]).sort();
    const varsAfter  = [...cssAfter .matchAll(/--color-[a-z0-9-]+(?:-rgb)?:/g)].map((m) => m[0]).sort();
    assert.deepEqual(varsBefore, varsAfter, 'token name set must be unchanged across swap');
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});
