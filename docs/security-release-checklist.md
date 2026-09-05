# Security release checklist

Before a hardening release is tagged:

- [ ] Full pytest suite passes on every supported validation Python version.
- [ ] Security regression suite passes.
- [ ] Source and installed import-contract checks pass.
- [ ] Exact built wheel passes CLI, Model IR, advanced-family, portable-export, surrogate, and LaTeX smoke contracts.
- [ ] Cross-platform wheel CLI jobs pass on Linux, Windows, and macOS.
- [ ] Documentation builds in strict mode.
- [ ] Dependency audit reports no known vulnerable runtime/test packages accepted by the project.
- [ ] Release preflight passes on the exact distributions that will be published.
- [ ] Version contract, PyPI Trusted Publishing, publication verification, and GitHub release creation remain intact.
