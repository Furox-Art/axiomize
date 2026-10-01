'use strict';

/**
 * npm package contract test for the Axiomize distribution shim.
 *
 * Runs under plain `npm test`, so it uses only Node built-ins. It asserts the
 * things a consumer of the npm package can observe without a Python install:
 *
 *   1. every shipped JavaScript file parses,
 *   2. the package manifest points at real files,
 *   3. the entry point exports a callable `runAxiomize`,
 *   4. the manifest stays in version lockstep with the Python distribution.
 *
 * The Python CLI itself is covered by the installed-wheel smoke gates
 * (`.github/scripts/cli_release_smoke.py`); this file deliberately does not
 * require a Python interpreter.
 */

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');

const ROOT = path.resolve(__dirname, '..', '..');

function parseFiles(relativePaths) {
  for (const relativePath of relativePaths) {
    const absolute = path.join(ROOT, relativePath);
    assert.ok(fs.existsSync(absolute), `missing shipped file: ${relativePath}`);
    execFileSync(process.execPath, ['--check', absolute], { stdio: 'pipe' });
    process.stdout.write(`PASS syntax ${relativePath}\n`);
  }
}

function testVersionLockstep() {
  const manifest = JSON.parse(fs.readFileSync(path.join(ROOT, 'package.json'), 'utf8'));
  const pyproject = fs.readFileSync(path.join(ROOT, 'pyproject.toml'), 'utf8');
  const match = pyproject.match(/^version\s*=\s*"([^"]+)"\s*$/m);
  assert.ok(match, 'pyproject.toml has no literal [project] version');
  const pythonVersion = match[1];

  assert.equal(
    manifest.version,
    pythonVersion,
    `package.json version ${manifest.version} != pyproject.toml version ${pythonVersion}`,
  );
  process.stdout.write(`PASS version lockstep npm=${manifest.version} python=${pythonVersion}\n`);

  const engine = manifest.engines && manifest.engines.node;
  assert.ok(engine, 'package.json must declare an engines.node range');
  assert.equal(engine, '>=18', `unexpected engines.node: ${engine}`);
  process.stdout.write(`PASS engines.node ${engine}\n`);

  const major = manifest.version.split('.')[0];
  const compat = manifest.axiomizeCompat;
  assert.ok(compat, 'package.json must declare axiomizeCompat');
  const expectedRange = `~> ${major}.0.0`;
  assert.equal(
    compat.npm,
    expectedRange,
    `axiomizeCompat.npm is ${compat.npm}, expected ${expectedRange}`,
  );
  assert.ok(compat.python, 'axiomizeCompat.python must be declared');
  process.stdout.write(`PASS axiomizeCompat npm=${compat.npm} python=${compat.python}\n`);
}

function testManifestPaths() {
  const manifest = JSON.parse(fs.readFileSync(path.join(ROOT, 'package.json'), 'utf8'));

  assert.equal(manifest.main, 'index.js', 'package.json main must be index.js');
  assert.ok(fs.existsSync(path.join(ROOT, manifest.main)), 'package.json main does not exist');

  for (const [name, target] of Object.entries(manifest.bin || {})) {
    assert.ok(fs.existsSync(path.join(ROOT, target)), `bin ${name} -> ${target} does not exist`);
    process.stdout.write(`PASS bin ${name} -> ${target}\n`);
  }

  const packedFiles = manifest.files;
  assert.ok(Array.isArray(packedFiles) && packedFiles.length > 0, 'package.json must declare a files allowlist');
  for (const entry of packedFiles) {
    assert.ok(
      fs.existsSync(path.join(ROOT, entry)),
      `files entry does not exist: ${entry}`,
    );
  }
  process.stdout.write(`PASS files allowlist (${packedFiles.length} entries)\n`);
}

function testEntrypointContract() {
  const entry = require(path.join(ROOT, 'index.js'));
  assert.equal(typeof entry.runAxiomize, 'function', 'index.js must export runAxiomize');
  assert.equal(entry.runAxiomize.length, 1, 'runAxiomize must accept an argv array');
  process.stdout.write('PASS runAxiomize export is callable\n');
}

const checks = [
  ['javascript syntax', () => parseFiles(['index.js', 'bin/axiomize.js'])],
  ['manifest paths', testManifestPaths],
  ['version lockstep', testVersionLockstep],
  ['entry point export', testEntrypointContract],
];

let failures = 0;
for (const [label, run] of checks) {
  try {
    run();
    process.stdout.write(`PASS ${label}\n`);
  } catch (err) {
    failures += 1;
    process.stdout.write(`FAIL ${label}: ${err.message}\n`);
  }
}

if (failures > 0) {
  process.stdout.write(`\nNPM CONTRACT: FAIL (${failures} failing check(s))\n`);
  process.exit(1);
}
process.stdout.write('\nNPM CONTRACT: PASS\n');
