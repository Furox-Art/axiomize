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
    const normalized = path.posix.normalize(target);
    assert.equal(
      target,
      normalized,
      `bin ${name} -> ${target} is not normalized; npm auto-corrects such entries at publish with a warning (use ${normalized})`,
    );
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
  const name = 'npm-publish.yml';
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
  const npmJobName = 'publish';
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

  // Neither npm publish step may fail silently, and every publish must carry
  // an explicit dist-tag so a prerelease cannot move `latest`.
  for (const label of ['Publish to npm (OIDC trusted publishing)', 'Publish to npm (NPM_TOKEN fallback)']) {
    const step = stepBody(npmJob, label);
    assert.ok(step, `${name}: could not locate the "${label}" step`);
    assert.ok(
      !/continue-on-error/.test(step),
      `${name}: "${label}" must not use continue-on-error; a failed npm publish must fail the release`,
    );
    assert.match(
      step,
      /--tag "\$\{\{ steps\.disttag\.outputs\.tag \}\}"/,
      `${name}: "${label}" must publish under the computed dist-tag`,
    );
  }
  assert.match(
    npmJob,
    /tag=next/,
    `${name}: a prerelease version must publish under the next dist-tag`,
  );

  // The job can obtain an npm identity and read source.
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

  assert.match(text, /use_token_fallback:[\s\S]*?default:\s*false/);
  assert.match(text, /use_token_fallback:[\s\S]*?type:\s*boolean/);
  assert.match(text, /inputs\.use_token_fallback[\s\S]*mode=token[\s\S]*else[\s\S]*mode=oidc/);
  assert.match(text, /NPM_TOKEN secret is empty/);
  assert.match(text, /cannot mint an OIDC token/);
  assert.match(text, /--registry-state/);
  for (const label of ['Publish to npm (OIDC trusted publishing)', 'Publish to npm (NPM_TOKEN fallback)']) {
    assert.match(stepBody(npmJob, label), /steps\.registry\.outputs\.exists != 'true'/);
  }

  const release = readWorkflow('release.yml');
  assert.ok(jobBlocks(release).has('publish'));
  assert.doesNotMatch(release, /npm publish --/);
  assert.match(release, /attestations:\s*true/);
  assert.doesNotMatch(release, /PYPI_API_TOKEN/);
  assert.match(release, /release-assets\/\*\.sbom\.spdx\.json/);
  process.stdout.write('PASS PyPI workflow retains attestations and the SBOM\n');
}

/**
 * The manual recovery path must publish the tagged release, not the tip of
 * main. After a release, main keeps moving: v1.14.2 differs from main in
 * README.md, package.json and tests/npm/contract.test.js, and all three ship in
 * the tarball. A dispatch-HEAD publish would therefore ship unreleased content
 * under an already-released version.
 */
function testPublishUsesTheTaggedRelease() {
  const text = readWorkflow('npm-publish.yml');

  assert.match(
    text,
    /version:\n\s+description:[\s\S]*?required:\s*true[\s\S]*?type:\s*string/,
    'npm-publish.yml: a required version input names the released tag to publish',
  );

  const jobs = jobBlocks(text);
  const releaseGate = jobs.get('release_gate');
  const job = jobs.get('publish');
  assert.ok(releaseGate && job, 'npm-publish.yml: the release gate and publish job are required');
  assert.match(text, /workflow_run:\s*\n\s*workflows: \[Release\]\s*\n\s*types: \[completed\]\s*\n\s*branches: \[main\]/);
  assert.match(releaseGate, /\.head_repository\.full_name/);
  assert.match(releaseGate, /\.github\/workflows\/release\.yml/);
  assert.match(releaseGate, /select\(\.name == "publish"\)/);
  assert.match(releaseGate, /"\$published" != "success"/);
  assert.match(job, /needs: release_gate/);
  assert.match(job, /PUBLISH_VERSION:.*inputs\.version \|\| needs\.release_gate\.outputs\.version/);
  assert.match(
    job,
    /ref:\s*refs\/tags\/v\$\{\{\s*env\.PUBLISH_VERSION\s*\}\}/,
    'npm-publish.yml: the checkout must pin the v<version> release tag',
  );
  assert.match(
    job,
    /fetch-depth:\s*0/,
    'npm-publish.yml: full history is required to prove the tag is on main',
  );

  const gateLabel = 'Verify the release tag, its ancestry and the PyPI release';
  const gate = stepBody(job, gateLabel);
  assert.ok(gate, 'npm-publish.yml: the release identity gate is missing');
  assert.match(gate, /"\$\(git rev-parse HEAD\)" != "\$RELEASE_SHA"/);
  assert.match(
    gate,
    /merge-base --is-ancestor HEAD origin\/main/,
    'npm-publish.yml: the tag commit must be proven to sit on main',
  );
  assert.ok(
    gate.includes('urllib.request.urlopen') && gate.includes('/pypi/{project}/{version}/json'),
    'npm-publish.yml: the released version must be proven live on PyPI before npm publish',
  );
  assert.match(
    gate,
    /raise SystemExit/,
    'npm-publish.yml: a version missing from PyPI must fail closed',
  );

  const gateIndex = text.indexOf(gateLabel);
  for (const label of ['Publish to npm (OIDC trusted publishing)', 'Publish to npm (NPM_TOKEN fallback)']) {
    const index = text.indexOf(label);
    assert.ok(index > gateIndex, `npm-publish.yml: "${label}" must run after the release identity gate`);
  }
  process.stdout.write('PASS npm-publish.yml: publishes the tagged release after proving it is on main and on PyPI\n');
}

const checks = [
  ['javascript syntax', () => parseFiles(['index.js', 'bin/axiomize.js'])],
  ['manifest paths', testManifestPaths],
  ['version lockstep', testVersionLockstep],
  ['entry point export', testEntrypointContract],
  ['publish modes', testPublishModes],
  ['publish uses the tested release tag', testPublishUsesTheTaggedRelease],
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