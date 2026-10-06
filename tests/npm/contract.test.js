'use strict';

/**
 * npm package contract test for the Axiomize distribution shim.
 *
 * Runs under plain `npm test`, so it uses only Node built-ins. It asserts the
 * things a consumer of the npm package can observe without a Python install,
 * plus the release-publish contract the workflows depend on:
 *
 *   1. every shipped JavaScript file parses,
 *   2. the package manifest points at real files,
 *   3. the entry point exports a callable `runAxiomize`,
 *   4. the manifest stays in version lockstep with the Python distribution,
 *   5. both publish modes exist, OIDC is the default, and the token path
 *      omits `--provenance`.
 */

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');

const ROOT = path.resolve(__dirname, '..', '..');
const WORKFLOWS = path.join(ROOT, '.github', 'workflows');

/** Minimal reader for the `on:`/inputs shape we assert on. */
function readWorkflow(name) {
  const file = path.join(WORKFLOWS, name);
  assert.ok(fs.existsSync(file), `missing workflow: ${name}`);
  return fs.readFileSync(file, 'utf8');
}

/**
 * Split a workflow into its job blocks, keyed by job id.
 *
 * A job starts at two-space indentation (`  jobname:`) and ends at the next
 * line with the same indentation. Anything shallower ends the `jobs:` section.
 */
function jobBlocks(text) {
  const lines = text.split('\n');
  const start = lines.findIndex((line) => /^jobs:\s*$/.test(line));
  const jobs = new Map();
  if (start === -1) return jobs;
  let current = null;
  let buffer = [];
  for (const line of lines.slice(start + 1)) {
    if (/^ {2}[a-zA-Z][\w-]*:\s*$/.test(line)) {
      if (current !== null) jobs.set(current, buffer.join('\n'));
      current = line.trim().replace(/:\s*$/, '');
      buffer = [line];
      continue;
    }
    if (/^\S/.test(line)) {
      // Dedented out of `jobs:` entirely.
      if (current !== null) jobs.set(current, buffer.join('\n'));
      current = null;
      buffer = [];
      continue;
    }
    if (current !== null) buffer.push(line);
  }
  if (current !== null) jobs.set(current, buffer.join('\n'));
  return jobs;
}

/**
 * Split a job into its step blocks and return the one whose `- name:` matches.
 * Comments are stripped so a comment mentioning a flag cannot satisfy — or
 * trip — an assertion about the step's real configuration.
 */
function stepBody(jobText, stepName) {
  const lines = jobText.split('\n');
  const starts = [];
  lines.forEach((line, index) => {
    if (/^ {6}- (?:name|uses|run):/.test(line)) starts.push(index);
  });
  for (let i = 0; i < starts.length; i += 1) {
    const begin = starts[i];
    const end = i + 1 < starts.length ? starts[i + 1] : lines.length;
    const block = lines.slice(begin, end).join('\n');
    if (block.startsWith(`      - name: ${stepName}`)) {
      return block
        .split('\n')
        .filter((line) => !/^\s*#/.test(line))
        .join('\n');
    }
  }
  return null;
}

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

/**
 * Both publish modes must be present, OIDC must be the default, and the token
 * path must not ask for provenance.
 */
function testPublishModes() {
  const workflows = ['release.yml', 'npm-publish.yml'];

  for (const name of workflows) {
    const text = readWorkflow(name);

    // Node 24 is required for both modes: npm's OIDC support needs
    // npm >= 11.5.1 / node >= 22.14.0, and node 20 ships npm 10.x.
    assert.match(
      text,
      /node-version:\s*"24"/,
      `${name}: node-version must stay 24 for trusted publishing`,
    );

    // Both modes are wired, selected by the same step output.
    assert.match(
      text,
      /if:\s*steps\.select-mode\.outputs\.mode == 'oidc'/,
      `${name}: missing the OIDC publish step`,
    );
    assert.match(
      text,
      /if:\s*steps\.select-mode\.outputs\.mode == 'token'/,
      `${name}: missing the NPM_TOKEN fallback publish step`,
    );

    // OIDC publishes with provenance and no token.
    assert.match(
      text,
      /npm publish --provenance --access public/,
      `${name}: OIDC publish must use --provenance`,
    );

    const jobs = jobBlocks(text);
    const npmJobName = name === 'release.yml' ? 'npm-package' : 'publish';
    const npmJob = jobs.get(npmJobName);
    assert.ok(npmJob, `${name}: could not locate the ${npmJobName} job`);

    // The token publish must omit --provenance: provenance is a Sigstore
    // attestation bound to the OIDC identity, so a long-lived token cannot
    // produce one and passing the flag fails the publish.
    const tokenStep = stepBody(npmJob, 'Publish to npm (NPM_TOKEN fallback)');
    assert.ok(tokenStep, `${name}: could not locate the NPM_TOKEN fallback step`);
    assert.ok(
      /npm publish --access public/.test(tokenStep),
      `${name}: the token publish must run 'npm publish --access public'`,
    );
    assert.ok(
      !/--provenance/.test(tokenStep),
      `${name}: the token publish must NOT pass --provenance; a long-lived token cannot mint a Sigstore attestation`,
    );
    assert.match(
      tokenStep,
      /NODE_AUTH_TOKEN: \$\{\{ secrets\.NPM_TOKEN \}\}/,
      `${name}: the token publish must set NODE_AUTH_TOKEN from secrets.NPM_TOKEN`,
    );

    const oidcStep = stepBody(npmJob, 'Publish to npm (OIDC trusted publishing)');
    assert.ok(oidcStep, `${name}: could not locate the OIDC publish step`);
    assert.ok(
      /npm publish --provenance --access public/.test(oidcStep),
      `${name}: the OIDC publish must run 'npm publish --provenance --access public'`,
    );
    assert.ok(
      !/NODE_AUTH_TOKEN/.test(oidcStep),
      `${name}: the OIDC publish must not set NODE_AUTH_TOKEN`,
    );

    // Neither npm publish step may fail silently. Scoped to each step's own
    // block: release.yml's PyPI publish steps legitimately use
    // continue-on-error for the trusted-publish -> token-fallback chain, and
    // those are guarded by an explicit "fail clearly" step instead.
    for (const label of ['Publish to npm (OIDC trusted publishing)', 'Publish to npm (NPM_TOKEN fallback)']) {
      const step = stepBody(npmJob, label);
      assert.ok(step, `${name}: could not locate the "${label}" step`);
      assert.ok(
        !/continue-on-error/.test(step),
        `${name}: "${label}" must not use continue-on-error; a failed npm publish must fail the release`,
      );
    }

    // Least privilege, scoped to the npm job. release.yml's separate `publish`
    // job does hold contents:write (it creates the GitHub release), so a
    // whole-file assertion would be wrong.
    assert.match(text, /id-token:\s*write/, `${name}: id-token:write is required for OIDC`);
    const perms = /^    permissions:\n((?:      .*\n)+)/m.exec(npmJob);
    assert.ok(perms, `${name}: ${npmJobName} must declare its own permissions block`);
    assert.match(perms[1], /id-token:\s*write/, `${name}: ${npmJobName} needs id-token:write for OIDC`);
    assert.match(perms[1], /contents:\s*read/, `${name}: ${npmJobName} needs contents:read to check out`);
    assert.ok(
      !/contents:\s*write/.test(perms[1]),
      `${name}: ${npmJobName} must not request contents:write; publishing does not need it`,
    );

    process.stdout.write(`PASS ${name}: both publish modes present, token path omits --provenance\n`);
  }

  // The manual workflow must expose the opt-in input and default it to false,
  // so OIDC stays the preferred path.
  const manual = readWorkflow('npm-publish.yml');
  assert.match(manual, /use_token_fallback:/, 'npm-publish.yml: missing use_token_fallback input');
  assert.match(
    manual,
    /use_token_fallback:[\s\S]*?default:\s*false/,
    'npm-publish.yml: use_token_fallback must default to false so OIDC is preferred',
  );
  assert.match(
    manual,
    /use_token_fallback:[\s\S]*?type:\s*boolean/,
    'npm-publish.yml: use_token_fallback must be a boolean input',
  );
  process.stdout.write('PASS npm-publish.yml: use_token_fallback input defaults to false (OIDC preferred)\n');

  // Automatic version-trigger pushes must use the repository's verified
  // token path directly; manual dispatches keep the explicit OIDC/token choice.
  const release = readWorkflow('release.yml');
  assert.match(
    release,
    /github\.event_name[\s\S]*workflow_dispatch[\s\S]*else[\s\S]*mode=token/,
    'release.yml: automatic push releases must select token mode',
  );
  assert.doesNotMatch(
    release,
    /vars\.npm_publish_mode/,
    'release.yml: automatic publishing must not depend on a repository variable',
  );
  process.stdout.write('PASS release.yml: automatic pushes use the verified token path\n');

  // Both modes must fail closed with an actionable message.
  for (const name of workflows) {
    const text = readWorkflow(name);
    assert.match(
      text,
      /NPM_TOKEN secret is empty/,
      `${name}: the token mode must fail closed when NPM_TOKEN is unset`,
    );
    assert.match(
      text,
      /cannot mint an OIDC token/,
      `${name}: the OIDC mode must fail closed when id-token:write was not granted`,
    );
  }
  process.stdout.write('PASS both modes fail closed with an actionable message\n');
}

const checks = [
  ['javascript syntax', () => parseFiles(['index.js', 'bin/axiomize.js'])],
  ['manifest paths', testManifestPaths],
  ['version lockstep', testVersionLockstep],
  ['entry point export', testEntrypointContract],
  ['publish modes', testPublishModes],
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