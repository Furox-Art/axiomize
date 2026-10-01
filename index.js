'use strict';

const { spawn } = require('child_process');

/**
 * Thin launcher for the Python `axiomize` CLI.
 *
 * The npm package is a distribution shim only: it locates a Python
 * interpreter, imports the installed `axiomize` package and forwards argv.
 * The Python side is validated by the release CLI smoke gates.
 */

// The Python module that owns `main()` and its `__main__` guard. Named once so
// the launcher cannot drift from the `axiomize = "axiomize.cli:main"` console
// script declared in pyproject.toml.
const CLI_MODULE = 'axiomize.cli';

function resolvePython() {
  return process.platform === 'win32' ? 'python' : 'python3';
}

function runAxiomize(args) {
  const proc = spawn(resolvePython(), ['-m', CLI_MODULE, ...args], {
    stdio: 'inherit',
    cwd: __dirname,
    // argv is forwarded as an array, so no shell is involved. State it anyway:
    // this file forwards attacker-influenced argv in a published package, and
    // an explicit `shell: false` keeps it that way under any future edit.
    shell: false,
    // Do not flash a console window on Windows for a CLI the user is watching.
    windowsHide: true,
  });

  // When the interpreter cannot be spawned Node emits 'error' *and then*
  // 'close'. Without this latch the close handler below overwrites the exit
  // status with the child's absent code - and if 'close' arrives with no
  // arguments at all, `process.exitCode` becomes undefined and the process
  // exits 0, reporting success for a command that never ran.
  let spawnFailed = false;

  // Surface a missing or broken interpreter instead of failing silently, so
  // `npx axiomize` reports the cause and exits non-zero.
  proc.on('error', (err) => {
    spawnFailed = true;
    process.stderr.write(`axiomize: failed to start Python interpreter: ${err.message}\n`);
    process.stderr.write(
      'axiomize: install Python 3.10+ and the axiomize package (`pip install axiomize`).\n',
    );
    process.exitCode = 127;
  });

  // Propagate the CLI exit status so scripts and CI can detect failure.
  proc.on('close', (code, signal) => {
    if (spawnFailed) {
      return; // keep the 127 recorded above
    }
    if (signal) {
      process.stderr.write(`axiomize: terminated by signal ${signal}\n`);
      process.exitCode = 1;
      return;
    }
    process.exitCode = code === null ? 1 : code;
  });

  return proc;
}

module.exports = { runAxiomize };

if (require.main === module) {
  runAxiomize(process.argv.slice(2));
}
