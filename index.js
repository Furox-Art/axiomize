'use strict';

const { spawn } = require('child_process');

/**
 * Thin launcher for the Python `axiomize` CLI.
 *
 * The npm package is a distribution shim only: it locates a Python
 * interpreter, imports the installed `axiomize` package and forwards argv.
 * The Python side is validated by the release CLI smoke gates.
 */
function resolvePython() {
  return process.platform === 'win32' ? 'python' : 'python3';
}

function runAxiomize(args) {
  const proc = spawn(resolvePython(), ['-m', 'axiomize.cli', ...args], {
    stdio: 'inherit',
    cwd: __dirname,
  });
  proc.on('error', (err) => {
    process.stderr.write(`axiomize: failed to start Python interpreter: ${err.message}\n`);
    process.exitCode = 127;
  });
  proc.on('close', (code, signal) => {
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
