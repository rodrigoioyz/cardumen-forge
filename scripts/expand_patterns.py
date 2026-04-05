#!/usr/bin/env python3
"""
expand_patterns.py — Cardumen Forge
For each .ak file in the DeFi families (16-25) of data/patterns/, generate up to 5
training variants with the same output (compiled code) but distinct instructions/inputs.

Usage:
    python3 scripts/expand_patterns.py
    python3 scripts/expand_patterns.py --dry-run
    python3 scripts/expand_patterns.py --families 16,17,18,19,20,21,22,23,24,25
    python3 scripts/expand_patterns.py --families all
    python3 scripts/expand_patterns.py --pattern 21e_order_fee_collection.ak
    python3 scripts/expand_patterns.py --max-success 200
    python3 scripts/expand_patterns.py --append-to data/processed/dataset_v23.jsonl
    python3 scripts/expand_patterns.py --dry-run --families 16,21,25 --append-to data/processed/dataset_v23.jsonl
"""

import os
import re
import sys
import json
import time
import hashlib
import argparse
import subprocess
from pathlib import Path
from datetime import datetime, timezone

ROOT         = Path(__file__).parent.parent
PATTERNS_DIR = ROOT / "data" / "patterns"
SANDBOX_DIR  = ROOT / "eval" / "aiken_sandbox"
SANDBOX_FILE = SANDBOX_DIR / "validators" / "output.ak"
OUT_DEFAULT  = ROOT / "data" / "processed" / "components" / "expanded_patterns.jsonl"
LOGS_DIR     = ROOT / "logs"
AIKEN_BIN    = os.path.expanduser("~/.aiken/bin/aiken")
AIKEN_CMD    = AIKEN_BIN if os.path.exists(AIKEN_BIN) else "aiken"
TIMEOUT_SECS = 120

DEFAULT_FAMILIES = [16, 17, 18, 19, 20, 21, 22, 23, 24, 25]

# ── Numeric prefix → topic category ──────────────────────────────────────────

CATEGORY_MAP = {
    "1":  "cardano/basics",
    "2":  "cardano/assets",
    "3":  "cardano/transaction",
    "4":  "cardano/validators",
    "5":  "aiken/collection/list",
    "6":  "aiken/collection/dict",
    "7":  "aiken/arithmetic",
    "8":  "aiken/crypto",
    "9":  "aiken/interval",
    "10": "cardano/address",
    "11": "cardano/certificates",
    "12": "cardano/governance",
    "13": "design_pattern/state_machine",
    "14": "design_pattern/cip68",
    "15": "design_pattern/reference_inputs",
    "16": "design_pattern/amm_lp",
    "17": "design_pattern/auction",
    "18": "design_pattern/vault",
    "19": "design_pattern/parameterized_vault",
    "20": "design_pattern/stablecoin",
    "21": "design_pattern/order_book",
    "22": "design_pattern/thread_nft",
    "23": "design_pattern/batch_swap",
    "24": "design_pattern/vesting",
    "25": "design_pattern/liquidation",
}


def topic_for(stem: str) -> str:
    """Derive topic string from file stem like '16b_lp_min_deposit'."""
    m = re.match(r'^(\d+)', stem)
    if m:
        cat = CATEGORY_MAP.get(m.group(1), "aiken/property_test")
        return f"property_test/{cat}"
    return "property_test/aiken"


def category_for(stem: str) -> str:
    """Return short category label like 'design_pattern/amm_lp'."""
    m = re.match(r'^(\d+)', stem)
    if m:
        return CATEGORY_MAP.get(m.group(1), "aiken/property_test")
    return "aiken/property_test"


def humanize_stem(stem: str) -> str:
    """'16b_lp_min_deposit' → 'LP minimum deposit'"""
    # Remove leading digits + optional letter + underscore
    label = re.sub(r'^\d+[a-z]?_', '', stem)
    label = label.replace('_', ' ')
    if label:
        label = label[0].upper() + label[1:]
    return label


# ── Instruction extraction ────────────────────────────────────────────────────

def extract_doc_comment(code: str) -> str:
    """Return the first /// doc-comment block as a single string."""
    lines = code.splitlines()
    doc_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("///"):
            doc_lines.append(stripped[3:].strip())
        elif doc_lines:
            break
    if doc_lines:
        text = " ".join(doc_lines).strip()
        if not text.endswith((".", "?", "!")):
            text += "."
        return text
    return ""


# ── Aiken sandbox runner (PTY — captures TTY output aiken writes directly) ────

ANSI = re.compile(r'\x1b(?:[@-Z\\-_]|\[[0-9;?]*[ -/]*[@-~])')

def run_aiken_check(code: str, max_success: int) -> dict:
    import pty, select
    SANDBOX_FILE.parent.mkdir(parents=True, exist_ok=True)
    SANDBOX_FILE.write_text(code, encoding="utf-8")
    start = time.time()
    try:
        master_fd, slave_fd = pty.openpty()
        proc = subprocess.Popen(
            [AIKEN_CMD, "check", f"--max-success={max_success}"],
            cwd=str(SANDBOX_DIR),
            stdin=slave_fd, stdout=slave_fd, stderr=slave_fd,
            close_fds=True,
        )
        os.close(slave_fd)
        buf = []
        deadline = time.time() + TIMEOUT_SECS
        while time.time() < deadline:
            r, _, _ = select.select([master_fd], [], [], 0.5)
            if r:
                try:
                    buf.append(os.read(master_fd, 4096).decode("utf-8", errors="replace"))
                except OSError:
                    break
            if proc.poll() is not None:
                break
        proc.wait(timeout=5)
        os.close(master_fd)
        elapsed = time.time() - start
        raw = ANSI.sub("", "".join(buf))
        lines = [l for l in raw.splitlines()
                 if not l.strip().startswith(("Compiling", "Downloading"))]
        return {
            "ok":      proc.returncode == 0,
            "output":  "\n".join(lines).strip(),
            "elapsed": round(elapsed, 2),
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "output": f"TIMEOUT after {TIMEOUT_SECS}s", "elapsed": TIMEOUT_SECS}
    except FileNotFoundError:
        return {"ok": False, "output": "aiken not found — check PATH", "elapsed": 0}


# ── Deduplication key ─────────────────────────────────────────────────────────

def record_key(rec: dict) -> str:
    """SHA256 of instruction + newline + output."""
    s = rec["instruction"] + "\n" + rec["output"]
    return hashlib.sha256(s.encode()).hexdigest()


# ── Code transformation helpers ───────────────────────────────────────────────

def strip_tests(code: str) -> str:
    """Remove all test blocks from the code. Returns code without any 'test ...' blocks."""
    lines = code.splitlines(keepends=True)
    result = []
    depth = 0
    in_test = False

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not in_test:
            # Detect start of a test block: line matches 'test <name>(...) {' or
            # 'test <name>(...) fail {' or 'test <name>() {' etc.
            # A test block begins with 'test ' at the start of a non-indented line
            # (or indented) and ends at the matching closing brace.
            if re.match(r'^\s*test\s+\w', line):
                in_test = True
                depth = 0
                # Count braces on this line
                depth += line.count('{') - line.count('}')
                i += 1
                continue
            else:
                result.append(line)
        else:
            depth += line.count('{') - line.count('}')
            if depth <= 0:
                in_test = False
        i += 1

    # Also remove trailing blank lines that resulted from test removal,
    # but keep the structure otherwise — just strip trailing whitespace.
    text = "".join(result)
    # Remove consecutive blank lines at end
    text = text.rstrip() + "\n"
    return text


def make_stub(code: str) -> str | None:
    """
    Replace the body of the first handler inside `validator ... { ... }` with `True`.
    Returns None if the validator block cannot be parsed with confidence.

    Handles: spend(...) { ... }, mint(...) { ... }, withdraw(...) { ... },
             else(_) { ... }, publish(...) { ... }, vote(...) { ... }
    """
    lines = code.splitlines(keepends=True)

    # Find `validator <name> {` line
    validator_start = None
    for i, line in enumerate(lines):
        if re.match(r'^\s*validator\s+\w+', line):
            validator_start = i
            break

    if validator_start is None:
        return None

    # Find the handler opening: spend/mint/withdraw/else/publish/vote
    HANDLER_RE = re.compile(
        r'^\s*(spend|mint|withdraw|else|publish|vote|propose)\s*\('
    )

    handler_line = None
    for i in range(validator_start, len(lines)):
        if HANDLER_RE.match(lines[i]):
            handler_line = i
            break

    if handler_line is None:
        return None

    # Find the opening brace of the handler body.
    # It could be on the same line as the handler, or on the next line.
    brace_line = None
    brace_col = None
    for i in range(handler_line, min(handler_line + 12, len(lines))):
        col = lines[i].find('{')
        if col != -1:
            # Make sure this is the body brace, not a brace inside parameter types
            # Simple heuristic: accept the first '{' at or after the closing ')' of params
            brace_line = i
            brace_col = col
            break

    if brace_line is None:
        return None

    # Now walk from brace_line forward to find the matching '}'
    depth = 0
    body_start = None   # first line after opening brace
    body_end = None     # line index of closing brace

    for i in range(brace_line, len(lines)):
        line = lines[i]
        if i == brace_line:
            # Count from brace_col onwards
            segment = line[brace_col:]
            opens = segment.count('{')
            closes = segment.count('}')
            depth += opens - closes
            if depth == 0:
                # Handler body is empty or on one line — not worth stubbing
                return None
            body_start = i + 1
        else:
            opens = line.count('{')
            closes = line.count('}')
            depth += opens - closes
            if depth == 0:
                body_end = i
                break

    if body_start is None or body_end is None:
        return None

    if body_end <= body_start:
        return None

    # Determine indentation for the stub body
    # Use the indentation of the first non-empty body line
    indent = "    "
    for i in range(body_start, body_end):
        stripped = lines[i].strip()
        if stripped:
            m = re.match(r'^(\s+)', lines[i])
            if m:
                indent = m.group(1)
            break

    # Build stubbed version
    stub_lines = (
        lines[:body_start]
        + [indent + "True\n"]
        + lines[body_end:]
    )

    stub = "".join(stub_lines)
    return stub


def extract_imports_and_types(code: str) -> str:
    """Return only `use ...` and `pub type ...` / `type ...` lines (and their bodies)."""
    lines = code.splitlines(keepends=True)
    result = []
    in_type = False
    depth = 0

    for line in lines:
        stripped = line.strip()

        if not in_type:
            if stripped.startswith("use "):
                result.append(line)
            elif re.match(r'^(pub\s+)?type\s+\w', stripped):
                in_type = True
                depth = line.count('{') - line.count('}')
                result.append(line)
                if depth == 0:
                    in_type = False
        else:
            result.append(line)
            depth += line.count('{') - line.count('}')
            if depth <= 0:
                in_type = False
                depth = 0

    return "".join(result).strip()


# ── Variant builders ──────────────────────────────────────────────────────────

def build_variants(path: Path) -> list[dict]:
    """
    Generate up to 5 training variants for the given .ak file.
    Returns list of record dicts (may be shorter than 5 if some variants are skipped).
    """
    code = path.read_text(encoding="utf-8")
    stem = path.stem
    category = category_for(stem)
    topic    = topic_for(stem)

    variants = []
    skip_notes = []

    # ── Shared fields template ─────────────────────────────────────────────────
    def make_rec(instruction, input_text, variant_name):
        return {
            "instruction":   instruction,
            "input":         input_text,
            "output":        code,
            "source":        "expand_patterns_v1",
            "topic":         topic,
            "variant":       variant_name,
            "review_status": "VERIFIED_FUZZ_PASS",
            "lang":          "en",
        }

    # ── Variant 1: implement ───────────────────────────────────────────────────
    doc = extract_doc_comment(code)
    if doc:
        instruction_1 = f"Write an Aiken v3 {category} validator: {doc}"
    else:
        label = humanize_stem(stem)
        instruction_1 = f"Write an Aiken v3 {category} validator for: {label}."
    variants.append(make_rec(instruction_1, "", "implement"))

    # ── Variant 2: complete_from_stub ─────────────────────────────────────────
    stub = make_stub(code)
    if stub is not None and stub != code:
        variants.append(make_rec(
            "Complete this Aiken v3 validator — replace the stub body with the real implementation:",
            stub,
            "complete_from_stub",
        ))
    else:
        reason = "no validator handler found" if stub is None else "stub identical to output"
        skip_notes.append(f"stub skipped: {reason}")

    # ── Variant 3: add_fuzz_tests ─────────────────────────────────────────────
    code_no_tests = strip_tests(code)
    if code_no_tests.strip() != code.strip():
        variants.append(make_rec(
            "Add property-based fuzz tests to this Aiken v3 validator:",
            code_no_tests,
            "add_fuzz_tests",
        ))
    else:
        skip_notes.append("add_fuzz_tests skipped: no test blocks found")

    # ── Variant 4: impl_from_description ─────────────────────────────────────
    human_name = humanize_stem(stem)
    variants.append(make_rec(
        f"Implement an Aiken v3 smart contract for {human_name}. Include property-based fuzz tests.",
        "",
        "impl_from_description",
    ))

    # ── Variant 5: complete_from_imports ─────────────────────────────────────
    imports_types = extract_imports_and_types(code)
    # Only add if we have at least 2 lines of meaningful content
    if imports_types and len(imports_types.splitlines()) >= 2:
        variants.append(make_rec(
            "Given these imports and types, implement the Aiken v3 validator and add property tests:",
            imports_types,
            "complete_from_imports",
        ))
    else:
        skip_notes.append("complete_from_imports skipped: too few imports/types")

    return variants, skip_notes


# ── File family filter ────────────────────────────────────────────────────────

def stem_family(stem: str) -> int | None:
    """Return the numeric family prefix of a stem, e.g. '16b_...' → 16."""
    m = re.match(r'^(\d+)', stem)
    if m:
        return int(m.group(1))
    return None


def collect_files(patterns_dir: Path, families: list[int] | None, pattern: str | None) -> list[Path]:
    if pattern:
        return [patterns_dir / pattern]

    all_files = sorted(patterns_dir.glob("*.ak"))
    if families is None:
        return all_files

    result = []
    for f in all_files:
        fam = stem_family(f.stem)
        if fam is not None and fam in families:
            result.append(f)
    return result


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Generate 5 training variants per .ak pattern file."
    )
    parser.add_argument(
        "--patterns",    default=str(PATTERNS_DIR),
        help="Directory with .ak pattern files",
    )
    parser.add_argument(
        "--pattern",     default=None,
        help="Process only this single file (by filename)",
    )
    parser.add_argument(
        "--families",    default=",".join(str(f) for f in DEFAULT_FAMILIES),
        help="Comma-separated family numbers to process, or 'all'",
    )
    parser.add_argument(
        "--max-success", type=int, default=200,
        help="aiken check --max-success value",
    )
    parser.add_argument(
        "--out",         default=str(OUT_DEFAULT),
        help="Output component JSONL file",
    )
    parser.add_argument(
        "--append-to",   default=None,
        help="Append new records directly to this dataset file",
    )
    parser.add_argument(
        "--dry-run",     action="store_true",
        help="Run checks and show variants but don't write anything",
    )
    args = parser.parse_args()

    patterns_dir = Path(args.patterns)
    if not patterns_dir.exists():
        print(f"Patterns dir not found: {patterns_dir}")
        sys.exit(1)

    # Parse --families
    if args.pattern:
        families = None  # ignored when --pattern is given
    elif args.families.strip().lower() == "all":
        families = None
    else:
        try:
            families = [int(x.strip()) for x in args.families.split(",")]
        except ValueError:
            print(f"Invalid --families value: {args.families}")
            sys.exit(1)

    files = collect_files(patterns_dir, families, args.pattern)

    if not files:
        print(f"No .ak files matched in {patterns_dir}")
        sys.exit(1)

    # Determine family range string for header
    if families:
        fam_str = f"families: {min(families)}-{max(families)}"
    else:
        fam_str = "all families"

    print(f"\n{'═'*65}")
    print(f"  expand_patterns — {len(files)} files ({fam_str})")
    print(f"  max-success={args.max_success}  variants=5  dry-run={args.dry_run}")
    print(f"{'═'*65}\n")

    all_generated: list[dict] = []
    files_pass = 0
    files_fail = 0
    total_variants = 0

    for i, path in enumerate(files, 1):
        if not path.exists():
            print(f"[{i:3d}/{len(files)}] ⚠️  {path.name} — not found, skipped")
            continue

        print(f"[{i:3d}/{len(files)}] ⏳  {path.stem:<50}", end="", flush=True)
        code = path.read_text(encoding="utf-8")
        res = run_aiken_check(code, args.max_success)

        if not res["ok"]:
            files_fail += 1
            print(
                f"\r[{i:3d}/{len(files)}] ❌  {path.stem:<50} {res['elapsed']:5.1f}s"
                f"  (compile fail — skip all variants)"
            )
            # Show first relevant error line
            for line in res["output"].splitlines():
                s = line.strip()
                if s and any(kw in s.lower() for kw in ("error", "×", "unexpected", "unknown")):
                    print(f"        ↳ {s[:110]}")
                    break
            continue

        files_pass += 1

        # Build variants
        file_variants, skip_notes = build_variants(path)
        n = len(file_variants)
        total_variants += n

        suffix = ""
        if skip_notes:
            suffix = f"  ({'; '.join(skip_notes)})"

        print(
            f"\r[{i:3d}/{len(files)}] ✅  {path.stem:<50} {res['elapsed']:5.1f}s"
            f"  → {n} variant{'s' if n != 1 else ''}{suffix}"
        )

        all_generated.extend(file_variants)

    # ── Summary ───────────────────────────────────────────────────────────────
    avg = total_variants / files_pass if files_pass > 0 else 0.0
    print(f"\n{'═'*65}")
    print(f"  Files:    {len(files)} processed  {files_pass} pass  {files_fail} fail")
    print(f"  Variants: {total_variants} generated  (avg {avg:.1f} per file)")

    if args.dry_run:
        print(f"  (dry-run — nothing written)")
        print(f"{'═'*65}\n")
        return

    if not all_generated:
        print(f"  Nothing to write.")
        print(f"{'═'*65}\n")
        return

    # ── Write component file ──────────────────────────────────────────────────
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for rec in all_generated:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"  Component → {out_path} ({len(all_generated)} records)")

    # ── Optionally append to a dataset ───────────────────────────────────────
    if args.append_to:
        dest = Path(args.append_to)
        if not dest.exists():
            print(f"  ⚠️  --append-to target not found: {dest}")
        else:
            # Dedup by SHA256(instruction + "\n" + output)
            existing_keys: set[str] = set()
            with open(dest, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        existing_keys.add(record_key(json.loads(line)))
                    except Exception:
                        pass

            new_records = [r for r in all_generated if record_key(r) not in existing_keys]
            dupes = len(all_generated) - len(new_records)

            if new_records:
                with open(dest, "a", encoding="utf-8") as f:
                    for rec in new_records:
                        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                print(f"  Appended → {dest} (+{len(new_records)} new, {dupes} dupes skipped)")
            else:
                print(
                    f"  All {len(all_generated)} records already present"
                    f" in {dest.name} — nothing appended"
                )

    # ── Save failure log ──────────────────────────────────────────────────────
    print(f"{'═'*65}\n")


if __name__ == "__main__":
    main()
