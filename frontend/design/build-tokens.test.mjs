// frontend/design/build-tokens.test.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { parseDesignMd, generateCss, generateTailwindJs, buildTokens, checkTokens } from './build-tokens.mjs';
import { mkdtemp, rm, writeFile, readFile, stat } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const MINIMAL = resolve(__dirname, 'fixtures/minimal-valid.md');
const MISSING  = resolve(__dirname, 'fixtures/missing-section.md');
const BAD_HEX  = resolve(__dirname, 'fixtures/bad-hex.md');
const WRONG_CO = resolve(__dirname, 'fixtures/wrong-columns.md');

test('parseDesignMd: happy path — returns the 17 color roles with hex values', async () => {
  const tokens = await parseDesignMd(MINIMAL);
  assert.equal(tokens.colors['bg.base'],        '#000000');
  assert.equal(tokens.colors['bg.surface'],     '#FFFFFF');
  assert.equal(tokens.colors['accent.primary'], '#6366F1');
  assert.equal(tokens.colors['accent.warning'], '#F59E0B');
  assert.equal(tokens.colors['chart.5'],        '#555555');
  assert.equal(Object.keys(tokens.colors).length, 17);
});

test('parseDesignMd: typography — sans and mono families with fallbacks', async () => {
  const tokens = await parseDesignMd(MINIMAL);
  assert.equal(tokens.typography.sans.family, 'Inter');
  assert.equal(tokens.typography.sans.fallback, 'ui-sans-serif, system-ui');
  assert.equal(tokens.typography.mono.family, 'JetBrains Mono');
  assert.equal(tokens.typography.mono.fallback, 'ui-monospace, Menlo');
});

test('parseDesignMd: elevation — radius, card shadow, 4 glow shadows', async () => {
  const tokens = await parseDesignMd(MINIMAL);
  assert.equal(tokens.elevation['radius.card'],         '1rem');
  assert.equal(tokens.elevation['shadow.card'],         '0 25px 50px -12px rgba(0,0,0,0.25)');
  assert.equal(tokens.elevation['shadow.glow.primary'], '0 0 20px rgba(99,102,241,0.15)');
  assert.equal(tokens.elevation['shadow.glow.danger'],  '0 0 20px rgba(244,63,94,0.15)');
  assert.equal(tokens.elevation['shadow.glow.warning'], '0 0 20px rgba(245,158,11,0.15)');
  assert.equal(tokens.elevation['shadow.glow.success'], '0 0 20px rgba(16,185,129,0.15)');
});

test('parseDesignMd: throws on missing required section', async () => {
  await assert.rejects(
    () => parseDesignMd(MISSING),
    /missing required section 'Color Palette & Roles'/
  );
});

test('parseDesignMd: throws on bad hex value with line number', async () => {
  await assert.rejects(
    () => parseDesignMd(BAD_HEX),
    /bad hex value '#XYZ' in role 'accent\.primary'/
  );
});

test('parseDesignMd: throws on wrong column count', async () => {
  await assert.rejects(
    () => parseDesignMd(WRONG_CO),
    /wrong column count/
  );
});

test('generateCss: emits :root block with hex and -rgb variants', async () => {
  const tokens = await parseDesignMd(MINIMAL);
  const css = generateCss(tokens);
  assert.match(css, /^\/\* GENERATED/);
  assert.match(css, /:root \{/);
  assert.match(css, /--color-bg-base:\s+#000000;/);
  assert.match(css, /--color-bg-base-rgb:\s+0 0 0;/);
  assert.match(css, /--color-accent-primary:\s+#6366F1;/);
  assert.match(css, /--color-accent-primary-rgb:\s+99 102 241;/);
  assert.match(css, /--color-chart-5-rgb:\s+85 85 85;/);
  assert.match(css, /--font-sans:\s+'Inter', ui-sans-serif, system-ui;/);
  assert.match(css, /--font-mono:\s+'JetBrains Mono', ui-monospace, Menlo;/);
  assert.match(css, /--radius-card:\s+1rem;/);
  assert.match(css, /--shadow-card:\s+0 25px 50px -12px rgba\(0,0,0,0\.25\);/);
  assert.match(css, /--shadow-glow-warning:\s+0 0 20px rgba\(245,158,11,0\.15\);/);
});

test('generateTailwindJs: exports designTokens object with semantic + legacy color names', async () => {
  const tokens = await parseDesignMd(MINIMAL);
  const js = generateTailwindJs(tokens);
  assert.match(js, /^\/\* GENERATED/);
  assert.match(js, /export const designTokens = \{/);
  assert.match(js, /'bg-base':\s+'rgb\(var\(--color-bg-base-rgb\) \/ <alpha-value>\)'/);
  assert.match(js, /'accent-primary':\s+'rgb\(var\(--color-accent-primary-rgb\) \/ <alpha-value>\)'/);
  assert.match(js, /'accent-warning':\s+'rgb\(var\(--color-accent-warning-rgb\) \/ <alpha-value>\)'/);
  assert.match(js, /'chart-5':\s+'rgb\(var\(--color-chart-5-rgb\) \/ <alpha-value>\)'/);
  // Legacy aliases
  assert.match(js, /obsidian:\s+'rgb\(var\(--color-bg-base-rgb\) \/ <alpha-value>\)'/);
  assert.match(js, /'indigo-glow':\s+'rgb\(var\(--color-accent-primary-rgb\) \/ <alpha-value>\)'/);
  assert.match(js, /'rose-glow':\s+'rgb\(var\(--color-accent-danger-rgb\) \/ <alpha-value>\)'/);
  assert.match(js, /'emerald-glow':\s+'rgb\(var\(--color-accent-success-rgb\) \/ <alpha-value>\)'/);
  assert.match(js, /sans:\s+\['var\(--font-sans\)'\]/);
  assert.match(js, /card:\s+'var\(--radius-card\)'/);
  assert.match(js, /'glow-primary':\s+'var\(--shadow-glow-primary\)'/);
  assert.match(js, /'glow-warning':\s+'var\(--shadow-glow-warning\)'/);
});

test('buildTokens: writes both generated files on first run', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'dt-'));
  try {
    const cssPath = join(dir, 'tokens.generated.css');
    const jsPath  = join(dir, 'tailwind.tokens.generated.js');
    const result = await buildTokens({
      source: MINIMAL,
      cssOut: cssPath,
      jsOut:  jsPath,
    });
    assert.equal(result.cssWritten, true);
    assert.equal(result.jsWritten,  true);
    const css = await readFile(cssPath, 'utf8');
    const js  = await readFile(jsPath,  'utf8');
    assert.match(css, /--color-accent-primary:\s+#6366F1;/);
    assert.match(js,  /'accent-primary':/);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test('buildTokens: idempotent — second run with unchanged source performs no writes', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'dt-'));
  try {
    const cssPath = join(dir, 'tokens.generated.css');
    const jsPath  = join(dir, 'tailwind.tokens.generated.js');
    await buildTokens({ source: MINIMAL, cssOut: cssPath, jsOut: jsPath });
    const statBefore = await stat(cssPath);
    // Small delay so mtime would differ if a write happened
    await new Promise((r) => setTimeout(r, 20));
    const result = await buildTokens({ source: MINIMAL, cssOut: cssPath, jsOut: jsPath });
    assert.equal(result.cssWritten, false);
    assert.equal(result.jsWritten,  false);
    const statAfter = await stat(cssPath);
    assert.equal(statBefore.mtimeMs, statAfter.mtimeMs);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test('checkTokens: returns {ok: true} when generated files match expected output', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'dt-'));
  try {
    const cssPath = join(dir, 'tokens.generated.css');
    const jsPath  = join(dir, 'tailwind.tokens.generated.js');
    await buildTokens({ source: MINIMAL, cssOut: cssPath, jsOut: jsPath });
    const result = await checkTokens({ source: MINIMAL, cssOut: cssPath, jsOut: jsPath });
    assert.equal(result.ok, true);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test('checkTokens: returns {ok: false, diff} when CSS is stale', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'dt-'));
  try {
    const cssPath = join(dir, 'tokens.generated.css');
    const jsPath  = join(dir, 'tailwind.tokens.generated.js');
    await buildTokens({ source: MINIMAL, cssOut: cssPath, jsOut: jsPath });
    await writeFile(cssPath, '/* tampered */\n');
    const result = await checkTokens({ source: MINIMAL, cssOut: cssPath, jsOut: jsPath });
    assert.equal(result.ok, false);
    assert.match(result.reason, /tokens\.generated\.css/);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});
