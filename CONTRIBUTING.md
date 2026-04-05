# Contributing

## Overview

This repo contains a fine-tuning dataset for Cardano smart contract development,
focused on Aiken, Hydra, and CIPs. The main layout:

- `data/raw/` — source JSON files (stdlib index, CIP specs, etc.)
- `data/patterns/` — Aiken snippet patterns (`.ak` files)
- `data/processed/` — versioned JSONL datasets
- `scripts/` — generation, cleaning, and audit tooling
- `eval/aiken_sandbox/` — Aiken project used to compile-check examples

## Adding examples to the dataset

Every new example must compile without errors. Before submitting:

1. Copy the validator or snippet into `eval/aiken_sandbox/` and run:
   ```
   aiken check
   ```
2. Fix any errors until `aiken check` exits cleanly.
3. To understand how examples are generated and structured, read the scripts
   under `scripts/` (e.g. `scripts/patterns_to_dataset.py`).

Do not add examples that only pass with `--skip-tests` or that require
commenting out parts of the code.

## Adding patterns

Pattern files (`.ak`) go in `data/patterns/`. Each file must:

- Compile cleanly with property tests enabled:
  ```
  aiken check --max-success=200
  ```
- Cover a single coherent concept or validator variant.
- Follow the naming convention already present in the directory.

## Pull request checklist

Before opening a PR, verify:

- [ ] `aiken check` passes in `eval/aiken_sandbox/` for every touched example.
- [ ] No temporary run logs are included (`logs/*.json`, `logs/*.txt` that were
      generated during a local audit run).
- [ ] No backup files are included (`.pre_*.jsonl`, `*.ref_backup`, etc.).
- [ ] Dataset version in `data/processed/` is bumped if the JSONL content changed.
- [ ] Commit messages are clear and reference the dataset version when relevant.

## Reporting issues

Use GitHub Issues. When reporting a compilation error, always include:

- The full output of `aiken check` (paste as a code block).
- The Aiken version (`aiken --version`).
- The example ID or snippet that triggers the error.

For dataset quality issues (wrong answer, misleading explanation), include the
example index and a brief description of what is wrong and what the correct
behavior should be.
