// frontend/design/build-tokens.mjs
// GENERATED DESCRIPTIONS: see frontend/design/schema.md for the strict grammar.
import { readFile } from 'node:fs/promises';

const REQUIRED_COLOR_ROLES = [
  'bg.base', 'bg.surface', 'border.subtle',
  'text.primary', 'text.secondary', 'text.muted',
  'accent.primary', 'accent.danger', 'accent.warning', 'accent.success',
  'selection.bg', 'selection.text',
  'chart.1', 'chart.2', 'chart.3', 'chart.4', 'chart.5',
];

const REQUIRED_TYPO_ROLES = ['sans', 'mono'];
const REQUIRED_ELEVATION_ROLES = [
  'radius.card', 'shadow.card',
  'shadow.glow.primary', 'shadow.glow.danger',
  'shadow.glow.warning', 'shadow.glow.success',
];

const HEX_RE = /^#[0-9A-Fa-f]{6}$/;

/**
 * Parse a DESIGN.md file into a structured tokens object.
 * Strict mode: throws on missing sections, bad hex values, missing roles.
 */
export async function parseDesignMd(path) {
  const source = await readFile(path, 'utf8');
  const lines = source.split('\n');

  // Colors
  const colorTable = extractSectionTable(lines, 'Color Palette & Roles', 3, path);
  const colors = {};
  for (const { cells, lineNo } of colorTable) {
    const [role, hex] = cells;
    if (!HEX_RE.test(hex)) {
      throw new Error(`${path}:${lineNo}: bad hex value '${hex}' in role '${role}'`);
    }
    colors[role] = hex;
  }
  for (const role of REQUIRED_COLOR_ROLES) {
    if (!(role in colors)) {
      throw new Error(`${path}: missing required role '${role}' in 'Color Palette & Roles'`);
    }
  }

  // Typography
  const typoTable = extractSectionTable(lines, 'Typography Rules', 3, path);
  const typography = {};
  for (const { cells, lineNo } of typoTable) {
    const [role, family, fallback] = cells;
    if (!REQUIRED_TYPO_ROLES.includes(role)) {
      throw new Error(`${path}:${lineNo}: unknown role '${role}' in 'Typography Rules'`);
    }
    typography[role] = { family, fallback };
  }
  for (const role of REQUIRED_TYPO_ROLES) {
    if (!(role in typography)) {
      throw new Error(`${path}: missing required role '${role}' in 'Typography Rules'`);
    }
  }

  // Elevation
  const elevTable = extractSectionTable(lines, 'Depth & Elevation', 2, path);
  const elevation = {};
  for (const { cells, lineNo } of elevTable) {
    const [role, value] = cells;
    elevation[role] = value;
  }
  for (const role of REQUIRED_ELEVATION_ROLES) {
    if (!(role in elevation)) {
      throw new Error(`${path}: missing required role '${role}' in 'Depth & Elevation'`);
    }
  }

  return { colors, typography, elevation };
}

/**
 * Find a `##` section by heading, then return the rows of the first markdown
 * table inside it. Each row is `{ cells: string[], lineNo: number }`.
 */
function extractSectionTable(lines, headingName, expectedCols, path) {
  const headingRe = new RegExp(`^##\\s+${escapeRe(headingName)}\\s*$`, 'i');
  let inSection = false;
  let sectionLine = -1;
  let inTable = false;
  let headerSeen = false;
  const rows = [];

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const lineNo = i + 1;

    if (headingRe.test(line)) {
      inSection = true;
      sectionLine = lineNo;
      continue;
    }
    if (inSection && /^##\s+/.test(line)) {
      break; // next section — stop
    }
    if (!inSection) continue;

    const isTableRow = /^\|.*\|\s*$/.test(line);
    if (!inTable && isTableRow) {
      inTable = true;
      headerSeen = false;
    }
    if (inTable && !isTableRow) {
      inTable = false;
      continue;
    }
    if (!inTable) continue;

    // Separator row like `|---|---|`
    if (/^\|\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|\s*$/.test(line)) {
      continue;
    }
    const cells = line.slice(1, -1).split('|').map((c) => c.trim());
    if (!headerSeen) {
      headerSeen = true;
      if (cells.length !== expectedCols) {
        throw new Error(
          `${path}:${lineNo}: wrong column count in '${headingName}' header (expected ${expectedCols}, got ${cells.length})`
        );
      }
      continue;
    }
    if (cells.length !== expectedCols) {
      throw new Error(
        `${path}:${lineNo}: wrong column count in '${headingName}' (expected ${expectedCols}, got ${cells.length})`
      );
    }
    rows.push({ cells, lineNo });
  }

  if (sectionLine === -1) {
    throw new Error(`${path}: missing required section '${headingName}'`);
  }
  if (rows.length === 0) {
    throw new Error(`${path}:${sectionLine}: required section '${headingName}' has no table`);
  }
  return rows;
}

function escapeRe(str) {
  return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

const GEN_HEADER = '/* GENERATED — do not edit. Source: frontend/design/DESIGN.md */';

/**
 * Convert a dotted role name like 'accent.primary' to a CSS custom property
 * suffix like 'accent-primary'.
 */
function roleToKebab(role) {
  return role.replace(/\./g, '-');
}

/** '#6366F1' → '99 102 241' (space-separated, for rgb(var(--x) / alpha)) */
function hexToRgbTriple(hex) {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `${r} ${g} ${b}`;
}

export function generateCss(tokens) {
  const lines = [GEN_HEADER, ':root {'];
  for (const [role, hex] of Object.entries(tokens.colors)) {
    const k = roleToKebab(role);
    lines.push(`  --color-${k}: ${hex};`);
    lines.push(`  --color-${k}-rgb: ${hexToRgbTriple(hex)};`);
  }
  lines.push(`  --font-sans: '${tokens.typography.sans.family}', ${tokens.typography.sans.fallback};`);
  lines.push(`  --font-mono: '${tokens.typography.mono.family}', ${tokens.typography.mono.fallback};`);
  for (const [role, value] of Object.entries(tokens.elevation)) {
    const k = roleToKebab(role);
    lines.push(`  --${k}: ${value};`);
  }
  lines.push('}', '');
  return lines.join('\n');
}

const LEGACY_COLOR_ALIASES = {
  'obsidian':     'bg.base',
  'indigo-glow':  'accent.primary',
  'rose-glow':    'accent.danger',
  'emerald-glow': 'accent.success',
};

export function generateTailwindJs(tokens) {
  const lines = [
    GEN_HEADER,
    'export const designTokens = {',
    '  colors: {',
  ];
  for (const role of Object.keys(tokens.colors)) {
    const k = roleToKebab(role);
    lines.push(`    '${k}': 'rgb(var(--color-${k}-rgb) / <alpha-value>)',`);
  }
  for (const [alias, sourceRole] of Object.entries(LEGACY_COLOR_ALIASES)) {
    const k = roleToKebab(sourceRole);
    const key = alias.includes('-') ? `'${alias}'` : alias;
    lines.push(`    ${key}: 'rgb(var(--color-${k}-rgb) / <alpha-value>)',`);
  }
  lines.push('  },');
  lines.push('  fontFamily: {');
  lines.push("    sans: ['var(--font-sans)'],");
  lines.push("    mono: ['var(--font-mono)'],");
  lines.push('  },');
  lines.push('  borderRadius: {');
  lines.push("    card: 'var(--radius-card)',");
  lines.push('  },');
  lines.push('  boxShadow: {');
  lines.push("    card: 'var(--shadow-card)',");
  lines.push("    'glow-primary': 'var(--shadow-glow-primary)',");
  lines.push("    'glow-danger':  'var(--shadow-glow-danger)',");
  lines.push("    'glow-warning': 'var(--shadow-glow-warning)',");
  lines.push("    'glow-success': 'var(--shadow-glow-success)',");
  lines.push('  },');
  lines.push('};', '');
  return lines.join('\n');
}

import { writeFile, readFile as readFileFs } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, resolve as resolvePath } from 'node:path';
import process from 'node:process';

async function readOrNull(path) {
  try {
    return await readFileFs(path, 'utf8');
  } catch (e) {
    if (e.code === 'ENOENT') return null;
    throw e;
  }
}

/**
 * Parse DESIGN.md, generate CSS and JS, write ONLY if contents changed.
 * Returns { cssWritten, jsWritten } reporting whether each file was touched.
 */
export async function buildTokens({ source, cssOut, jsOut }) {
  const tokens = await parseDesignMd(source);
  const cssExpected = generateCss(tokens);
  const jsExpected  = generateTailwindJs(tokens);
  const [cssCurrent, jsCurrent] = await Promise.all([readOrNull(cssOut), readOrNull(jsOut)]);

  let cssWritten = false;
  let jsWritten  = false;
  if (cssCurrent !== cssExpected) {
    await writeFile(cssOut, cssExpected, 'utf8');
    cssWritten = true;
  }
  if (jsCurrent !== jsExpected) {
    await writeFile(jsOut, jsExpected, 'utf8');
    jsWritten = true;
  }
  return { cssWritten, jsWritten };
}

/**
 * Parse DESIGN.md, generate CSS and JS in memory, compare to committed files.
 * Returns { ok: true } when both match, { ok: false, reason } otherwise.
 */
export async function checkTokens({ source, cssOut, jsOut }) {
  const tokens = await parseDesignMd(source);
  const cssExpected = generateCss(tokens);
  const jsExpected  = generateTailwindJs(tokens);
  const [cssCurrent, jsCurrent] = await Promise.all([readOrNull(cssOut), readOrNull(jsOut)]);

  if (cssCurrent === null) return { ok: false, reason: `${cssOut} missing` };
  if (jsCurrent  === null) return { ok: false, reason: `${jsOut} missing` };
  if (cssCurrent !== cssExpected) {
    return { ok: false, reason: `${cssOut} is stale — run: npm run design:build` };
  }
  if (jsCurrent !== jsExpected) {
    return { ok: false, reason: `${jsOut} is stale — run: npm run design:build` };
  }
  return { ok: true };
}

// CLI entry point — run only when invoked directly
const isMain = import.meta.url === `file://${process.argv[1]}`;
if (isMain) {
  const here = dirname(fileURLToPath(import.meta.url));
  const frontend = resolvePath(here, '..');
  const paths = {
    source: resolvePath(here, 'DESIGN.md'),
    cssOut: resolvePath(frontend, 'src/styles/tokens.generated.css'),
    jsOut:  resolvePath(frontend, 'tailwind.tokens.generated.js'),
  };
  const isCheck = process.argv.includes('--check');
  try {
    if (isCheck) {
      const result = await checkTokens(paths);
      if (!result.ok) {
        console.error(`design:check failed: ${result.reason}`);
        process.exit(1);
      }
      console.log('design:check ok');
    } else {
      const result = await buildTokens(paths);
      const touched = [
        result.cssWritten ? 'tokens.generated.css' : null,
        result.jsWritten  ? 'tailwind.tokens.generated.js' : null,
      ].filter(Boolean);
      console.log(touched.length ? `design:build wrote ${touched.join(', ')}` : 'design:build no-op');
    }
  } catch (e) {
    console.error(String(e.message ?? e));
    process.exit(1);
  }
}
