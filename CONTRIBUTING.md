# Contributing

Start with [AGENTS.md](AGENTS.md), [setup](docs/SETUP.md), and
[development](docs/DEVELOPMENT.md). Keep changes focused, describe the user-visible
behavior, and include the checks you actually ran. The project currently targets
a local research workflow; the [roadmap](README.md#future-plan-from-research-workspace-to-everyday-reading)
describes the broader audience we hope to support.

Use temporary synthetic vaults for tests. Keep personal data, annotation exports,
API keys, pairing keys, and service configuration out of commits and screenshots.
Setup and baseline tests require no private credentials or model account.

Native client and worker changes belong in the existing nested checkouts. Export
the complete intended patches with `./hypothesis/build --export-patches`, then
build with `./hypothesis/build`. Commit the patches, not generated upstream
repositories or node_modules. Never overwrite existing work to repair a patch
mismatch. See the development guide for the targeted typecheck, lint, browser,
backend, and integration commands.

Use [the taxonomy source](research-partner/research_notes/taxonomy.json) for local
classification changes and regenerate its catalog. Keep manual labels independent
of derived results, retain provenance, and let ambiguous cases remain unknown.
Add external code/assets only with attribution and their required notices.
