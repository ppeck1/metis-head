# Export contents and exclusions

The release archive is built from the current working folder, not from git archive. It includes tracked files plus untracked application source, browser assets, tests, scripts, documentation, pyproject.toml, and sanitized local-helper templates.

Excluded: .git internals, .project private local configuration, credentials, OAuth client files/tokens, environment files, recordings, virtual environments, caches, build output, coverage output, prior exports, and model weights.
