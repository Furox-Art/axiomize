const { spawn } = require('child_process');

// The Python package owns the CLI; this wrapper only forwards argv. `axiomize.cli`
// is the module that owns `main()` and its `__main__` guard, matching the
// `axiomize = "axiomize.cli:main"` console script declared in pyproject.toml.
const CLI_MODULE = 'axiomize.cli';

function pythonExecutable() {
  return process.platform === 'win32' ? 'python' : 'python3';
}

function runAxiomize(args) {
  const proc = spawn(pythonExecutable(), ['-m', CLI_MODULE, ...args], {
    stdio: 'inherit',
    cwd: __dirname,
    shell: false,
    windowsHide: true,
  });

  // Surface a missing/broken interpreter instead of failing silently, otherwise
  // `npx axiomize` exits 0 while printing nothing.
  proc.on('error', (err) => {
    process.stderr.write(`axiomize: cannot start ${pythonExecutable()}: ${err.message}\n`);
    process.stderr.write('axiomize: install Python 3.10+ and the axiomize package (`pip install axiomize`).\n');
    process.exitCode = 127;
  });

  // Propagate the CLI exit status so scripts and CI can detect failure.
  proc.on('close', (code, signal) => {
    if (signal) {
      process.exitCode = 1;
      return;
    }
    process.exitCode = code === null ? 1 : code;
  });

  return proc;
}

module.exports = { runAxiomize, CLI_MODULE, pythonExecutable };

if (require.main === module) {
  runAxiomize(process.argv.slice(2));
}
