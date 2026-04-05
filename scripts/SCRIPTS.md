# Scripts Reference — Cardumen Forge

## Active Pipeline Scripts (scripts/)

### Fuzz Pattern Pipeline (new — v24)
| Script | Purpose |
|--------|---------|
| `test_patterns.py` | Sandbox harness: runs `aiken check` on every `.ak` in `data/patterns/` |
| `patterns_to_dataset.py` | Compile-gated ingestion: passing patterns → dataset records |

### Dataset Cleaning & Verification
| Script | Purpose |
|--------|---------|
| `audit_dataset_compile.py` | Run `aiken check` on every dataset example |
| `audit_dataset_quality.py` | Claude API quality review across all sources |
| `audit_structural_dupes.py` | Detect structurally similar outputs (normalized MD5) |
| `migrate_dataset_to_v3.py` | Stdlib v3 migration: pub type, API renames, auto-imports |
| `fix_fn_prefix.py` | `fn spend/mint/...` → remove `fn` prefix |
| `fix_types.py` | `ScriptCredential` → `Script`, `PolicyId` import fixes |
| `fix_import_keyword.py` | `import x.y.z` → `use x/y/z` |
| `fix_dataset_v23.py` | v23-specific fixes |
| `repair_dataset_v23.py` | Repair v23 examples via Claude API |
| `regenerate_failing.py` | Fix compile failures via Claude API |
| `regenerate_truncated.py` | Regenerate truncated outputs from source docs |
| `strip_markdown_outputs.py` | Extract code from markdown-fenced outputs |
| `dedup_dataset.py` | Two-pass dedup: exact hash + n-gram similarity |
| `compare_datasets.py` | Quality metrics comparison across versions |

### Example Generation
| Script | Purpose |
|--------|---------|
| `generate_governance_examples.py` | vote/publish/propose validators |
| `generate_reference_input_examples.py` | CIP-31 reference input patterns |
| `add_tests_to_verified.py` | Add `test` blocks to existing VERIFIED examples |
| `patch_positive_mints.py` | Fix positive mint patterns |
| `build_v16.py` | `fn else(` fixes + broken example removal |

### Review & Promotion
| Script | Purpose |
|--------|---------|
| `review_plausible.py` | PLAUSIBLE review via local stdlib check |
| `promote_plausible.py` | PLAUSIBLE → VERIFIED via compile + banned-pattern check |
| `fix_plausible_failures.py` | Claude API repair of compile failures |

---

## Subdirectories

| Dir | Step | Purpose |
|-----|------|---------|
| `scrape/` | 1 | Collect raw sources from GitHub/docs |
| `generate/` | 2 | Generate training examples via Claude API |
| `audit/` | 3 | API coverage + contamination checks |
| `build/` | 4 | Assemble and split dataset |
| `oneoff/` | — | Single-use investigation scripts (not part of pipeline) |

---

## oneoff/ — Investigation Scripts

These scripts were written to debug specific issues. They are preserved for reference but are **not part of the active pipeline**.

| Script | Original purpose |
|--------|-----------------|
| `analyze_audit.py` | Analyze audit output logs |
| `analyze_audit2.py` | Second-pass audit analysis |
| `analyze_audit3.py` | Third-pass audit analysis |
| `analyze_skipped.py` | Inspect skipped examples |
| `check_dp_fences.py` | Check design pattern code fences |
| `check_dp_snippets.py` | Check design pattern snippets |
| `check_handlers.py` | Inspect handler usage |
| `check_handlers2.py` | Handler inspection v2 |
| `check_stdlib.py` | Stdlib function verification |
| `check_types.py` | Type usage inspection |
| `fuzz_stats.py` | Fuzz test statistics |
| `inspect_correction_v2.py` | Inspect correction set v2 |
| `inspect_sources.py` | Source distribution inspection |
| `show_cv2_failures.py` | Show correction_set_v2 failures |
| `show_errors.py` | Show compile errors |
| `show_existing_handlers.py` | Show handler coverage |
