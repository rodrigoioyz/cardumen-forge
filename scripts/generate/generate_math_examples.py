#!/usr/bin/env python3
"""
generate_math_examples.py — Generate aiken/math and aiken/math/rational training examples
Fills coverage gap: math at 3.7%, rational underrepresented.

Usage:
    python3 scripts/generate/generate_math_examples.py
    python3 scripts/generate/generate_math_examples.py --n 40
    python3 scripts/generate/generate_math_examples.py --dry-run
"""

import os, re, pty, select, shutil, time, json, argparse, subprocess
from pathlib import Path
from datetime import datetime, timezone

import anthropic

ROOT         = Path(__file__).parent.parent.parent
SANDBOX_DIR  = ROOT / "eval" / "aiken_sandbox"
SANDBOX_FILE = SANDBOX_DIR / "validators" / "output.ak"
OUT_FILE     = ROOT / "data" / "processed" / "components" / "math_examples.jsonl"
LOGS_DIR     = ROOT / "logs" / "generate"
ANSI         = re.compile(r'\x1b(?:[@-Z\\-_]|\[[0-9;?]*[ -/]*[@-~])')
AIKEN_BIN    = shutil.which("aiken") or str(Path.home() / ".aiken" / "bin" / "aiken")
TIMEOUT_SECS = 30
MODEL        = "claude-sonnet-4-6"

SYSTEM_PROMPT = """\
You are an expert Aiken v3 smart contract developer.
Generate complete, compilable Aiken v3 validators that use aiken/math and aiken/math/rational.

── aiken/math API ──
  use aiken/math

  math.abs(n: Int) -> Int                         // absolute value
  math.clamp(n: Int, min: Int, max: Int) -> Int   // clamp between bounds
  math.gcd(a: Int, b: Int) -> Int                 // greatest common divisor
  math.max(a: Int, b: Int) -> Int                 // maximum of two ints
  math.min(a: Int, b: Int) -> Int                 // minimum of two ints
  math.pow(base: Int, exp: Int) -> Int            // integer exponentiation
  math.pow2(n: Int) -> Int                        // 2^n (optimized)
  math.sqrt(n: Int) -> Option<Int>               // integer square root (Babylonian)
  math.is_sqrt(n: Int, r: Int) -> Bool           // verify r == sqrt(n)
  math.log(n: Int, base: Int) -> Int             // integer log base
  math.log2(n: Int) -> Int                       // integer log base 2

── aiken/math/rational API ──
  use aiken/math/rational

  rational.new(numerator: Int, denominator: Int) -> Option<Rational>  // None if denom=0
  rational.from_int(n: Int) -> Rational
  rational.zero: Rational                         // 0/1
  rational.numerator(r: Rational) -> Int
  rational.denominator(r: Rational) -> Int

  rational.add(a: Rational, b: Rational) -> Rational
  rational.sub(a: Rational, b: Rational) -> Rational
  rational.mul(a: Rational, b: Rational) -> Rational
  rational.div(a: Rational, b: Rational) -> Option<Rational>
  rational.negate(r: Rational) -> Rational
  rational.abs(r: Rational) -> Rational
  rational.reduce(r: Rational) -> Rational        // simplify to lowest terms
  rational.reciprocal(r: Rational) -> Option<Rational>

  rational.compare(a: Rational, b: Rational) -> Ordering  // Less | Equal | Greater
  rational.compare_with(a, fn(Int,Int)->Bool, b) -> Bool  // custom comparison

  rational.floor(r: Rational) -> Int             // round down
  rational.ceil(r: Rational) -> Int              // round up
  rational.round(r: Rational) -> Int             // nearest
  rational.truncate(r: Rational) -> Int          // toward zero

  rational.pow(x: Rational, y: Int) -> Option<Rational>
  rational.arithmetic_mean(xs: List<Rational>) -> Option<Rational>
  rational.geometric_mean(a: Rational, b: Rational) -> Option<Rational>

── Ordering type ──
  // From rational.compare:
  when rational.compare(a, b) is {
    Less    -> ...
    Equal   -> ...
    Greater -> ...
  }

── rational.compare_with — signature ──
  // rational.compare_with(a: Rational, cmp: fn(Int, Int) -> Bool, b: Rational) -> Bool
  // Internally compares cross-products: cmp(a.num * b.den, b.num * a.den)
  // Use pattern matching for rational.new — NEVER use option.or_else:
  //   expect Some(r) = rational.new(num, den)   ✅
  //   rational.new(num, den) |> option.or_else(...)  ❌ (requires option import)
  // For rational.new(1, 2), use: expect Some(half) = rational.new(1, 2)

── Import rules — CRITICAL ──
  use statements at the TOP. Slash ONLY in use statements. NEVER in type annotations.

  WRONG: _ref: cardano/transaction.OutputReference   // ❌ slash in type annotation
  RIGHT: use cardano/transaction.{Transaction, OutputReference}
         then use bare OutputReference in handler    // ✅

  ALWAYS import OutputReference explicitly:
    use cardano/transaction.{Transaction, OutputReference}

  Handler signatures:
    spend(datum: Option<T>, _redeemer: Data, _ref: OutputReference, self: Transaction) -> Bool
    mint(redeemer: T, policy_id: PolicyId, self: Transaction) -> Bool

File structure: use statements, pub types, helper fns, validator.
Output ONLY raw Aiken source code. No markdown, no explanation."""

PROMPTS = [
    # math.abs
    ("Write an Aiken v3 spend validator `abs_threshold` with ThresholdDatum "
     "(value: Int, max_abs: Int). Use math.abs to verify |value| <= max_abs.",
     ["math.abs", "spend("]),

    # math.clamp
    ("Write an Aiken v3 spend validator `clamped_fee` with FeeDatum "
     "(raw_fee: Int, min_fee: Int, max_fee: Int, expected: Int). "
     "Use math.clamp(raw_fee, min_fee, max_fee) and verify the result equals expected.",
     ["math.clamp", "spend("]),

    # math.min / math.max
    ("Write an Aiken v3 spend validator `min_max_check` with BoundsDatum "
     "(a: Int, b: Int, must_use_min: Bool, threshold: Int). "
     "If must_use_min, verify math.min(a, b) >= threshold; otherwise math.max(a, b) <= threshold.",
     ["math.min", "math.max", "spend("]),

    ("Write an Aiken v3 spend validator `bounded_payment` with PaymentDatum "
     "(amount: Int, fee: Int, min_net: Int). "
     "Use math.max to compute the effective fee (fee or 0) and verify amount - effective_fee >= min_net.",
     ["math.max", "spend("]),

    # math.pow / math.pow2
    ("Write an Aiken v3 spend validator `power_threshold` with PowerDatum "
     "(base: Int, exponent: Int, min_result: Int). "
     "Use math.pow(base, exponent) and verify the result >= min_result.",
     ["math.pow", "spend("]),

    ("Write an Aiken v3 spend validator `bitshift_validator` with ShiftDatum "
     "(bits: Int, min_value: Int). "
     "Use math.pow2(bits) to compute 2^bits and verify >= min_value.",
     ["math.pow2", "spend("]),

    # math.sqrt / math.is_sqrt
    ("Write an Aiken v3 spend validator `sqrt_proof` with SqrtDatum "
     "(n: Int, claimed_sqrt: Int). "
     "Use math.is_sqrt(n, claimed_sqrt) to verify claimed_sqrt is the integer square root of n.",
     ["math.is_sqrt", "spend("]),

    ("Write an Aiken v3 spend validator `sqrt_bound` with BoundDatum "
     "(value: Int, max_sqrt: Int). "
     "Use math.sqrt(value) — if Some(r), verify r <= max_sqrt; if None, fail.",
     ["math.sqrt", "spend("]),

    # math.gcd
    ("Write an Aiken v3 spend validator `gcd_validator` with GcdDatum "
     "(a: Int, b: Int, expected_gcd: Int). "
     "Use math.gcd(a, b) and verify it equals expected_gcd.",
     ["math.gcd", "spend("]),

    ("Write an Aiken v3 spend validator `coprime_check` with CoprimesDatum "
     "(a: Int, b: Int). "
     "Use math.gcd(a, b) == 1 to verify a and b are coprime.",
     ["math.gcd", "spend("]),

    # math.log / math.log2
    ("Write an Aiken v3 spend validator `log_bound` with LogDatum "
     "(value: Int, base: Int, max_log: Int). "
     "Use math.log(value, base) and verify the result <= max_log.",
     ["math.log", "spend("]),

    ("Write an Aiken v3 spend validator `log2_tier` with TierDatum "
     "(amount: Int, max_tier: Int). "
     "Use math.log2(amount) to compute the tier and verify tier <= max_tier.",
     ["math.log2", "spend("]),

    # rational.new / basic arithmetic
    ("Write an Aiken v3 spend validator `ratio_check` with RatioDatum "
     "(numerator: Int, denominator: Int, min_ratio_num: Int, min_ratio_den: Int). "
     "Use rational.new to create both rationals and rational.compare to verify "
     "numerator/denominator >= min_ratio_num/min_ratio_den.",
     ["rational.new", "rational.compare", "spend("]),

    ("Write an Aiken v3 spend validator `fee_ratio_validator` with FeeDatum "
     "(amount: Int, fee: Int, max_fee_bps: Int). "
     "Use rational.new(fee, amount) and rational.new(max_fee_bps, 10000) and "
     "rational.compare to verify fee/amount <= max_fee_bps/10000.",
     ["rational.new", "rational.compare", "spend("]),

    # rational arithmetic
    ("Write an Aiken v3 spend validator `interest_calculator` with InterestDatum "
     "(principal: Int, rate_num: Int, rate_den: Int, min_interest: Int). "
     "Use rational.new(rate_num, rate_den) and rational.mul with rational.from_int(principal) "
     "to compute interest and verify rational.floor(interest) >= min_interest.",
     ["rational.new", "rational.mul", "rational.from_int", "rational.floor", "spend("]),

    ("Write an Aiken v3 spend validator `split_validator` with SplitDatum "
     "(total: Int, share_num: Int, share_den: Int, recipient_min: Int). "
     "Use rational.new and rational.mul to compute the share of total, "
     "then rational.floor to get the integer amount, verify >= recipient_min.",
     ["rational.new", "rational.mul", "rational.floor", "spend("]),

    # rational.reduce
    ("Write an Aiken v3 spend validator `reduced_fraction` with FractionDatum "
     "(num: Int, den: Int, expected_num: Int, expected_den: Int). "
     "Use rational.new, rational.reduce and verify numerator/denominator match expected.",
     ["rational.new", "rational.reduce", "rational.numerator", "rational.denominator", "spend("]),

    # rational.ceil / round
    ("Write an Aiken v3 spend validator `ceil_fee_validator` with CeilDatum "
     "(amount: Int, fee_bps: Int, max_fee: Int). "
     "Compute fee = rational.ceil(rational.mul(rational.new(fee_bps, 10000)!, rational.from_int(amount))) "
     "and verify fee <= max_fee. Use expect Some(r) = rational.new(fee_bps, 10000).",
     ["rational.new", "rational.mul", "rational.ceil", "rational.from_int", "spend("]),

    # rational.compare_with
    ("Write an Aiken v3 spend validator `ratio_above_half` with RatioDatum "
     "(num: Int, den: Int). "
     "Use rational.new and rational.compare_with with fn(a, b) { a * 2 > b } to verify "
     "the ratio is strictly greater than 1/2. "
     "Use 'expect Some(r) = rational.new(num, den)' and "
     "'expect Some(half) = rational.new(1, 2)' for safe unwrapping. "
     "Do NOT use option.or_else.",
     ["rational.new", "rational.compare_with", "spend("]),

    # combined math + rational
    ("Write an Aiken v3 spend validator `compound_math` with MathDatum "
     "(base: Int, exp: Int, divisor: Int, min_result: Int). "
     "Compute val = math.pow(base, exp). Use rational.new(val, divisor) and "
     "rational.floor to get the integer quotient, verify >= min_result.",
     ["math.pow", "rational.new", "rational.floor", "spend("]),
]


def compile_check(code: str) -> tuple[bool, str]:
    SANDBOX_FILE.write_text(code, encoding="utf-8")
    try:
        master_fd, slave_fd = pty.openpty()
        proc = subprocess.Popen(
            [AIKEN_BIN, "check", "--max-success", "0"],
            cwd=str(SANDBOX_DIR), stdin=slave_fd, stdout=slave_fd, stderr=slave_fd, close_fds=True,
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
        return proc.returncode == 0, ANSI.sub("", "".join(buf))
    except Exception as e:
        return False, str(e)


def generate_one(client, prompt: str) -> str | None:
    instruction = (
        f"{prompt}\n\n"
        "Return ONLY the complete Aiken source file. "
        "No explanation, no markdown. Start with the first line."
    )
    try:
        resp = client.messages.create(
            model=MODEL, max_tokens=2000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": instruction}],
        )
        result = resp.content[0].text.strip()
        if result.startswith("```"):
            result = re.sub(r'^```[a-z]*\n?', '', result)
            result = re.sub(r'\n?```$', '', result)
        return result
    except Exception as e:
        print(f"    API error: {e}")
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=len(PROMPTS))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    client = None if args.dry_run else anthropic.Anthropic()
    prompts = PROMPTS[:args.n]

    already_done = set()
    if OUT_FILE.exists():
        with OUT_FILE.open() as f:
            for line in f:
                try:
                    already_done.add(json.loads(line)["instruction"])
                except Exception:
                    pass
    if already_done:
        print(f"Skipping {len(already_done)} already-verified prompts")

    passed, failed_list = 0, []
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    for i, (prompt, must_contain) in enumerate(prompts):
        if prompt in already_done:
            print(f"[{i+1}/{len(prompts)}] skip (already verified)")
            continue
        print(f"[{i+1}/{len(prompts)}] {prompt[:80]}...")
        if args.dry_run:
            print("  [dry-run] skip")
            continue

        code = generate_one(client, prompt)
        if not code:
            failed_list.append({"prompt": prompt, "error": "API returned None"})
            continue

        missing = [kw for kw in must_contain if kw not in code]
        if missing:
            print(f"  ✗ missing keywords: {missing}")
            failed_list.append({"prompt": prompt, "error": f"missing: {missing}", "code": code})
            continue

        ok, output = compile_check(code)
        if ok:
            print(f"  ✓ compile ok")
            record = {
                "instruction": prompt,
                "input": "",
                "output": code,
                "source": "generate/math_examples",
                "topic": "aiken/math",
                "review_status": "VERIFIED",
                "lang": "en",
            }
            with OUT_FILE.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
            passed += 1
        else:
            print(f"  ✗ compile error")
            failed_list.append({"prompt": prompt, "error": output[:500], "code": code})

    if failed_list:
        log_path = LOGS_DIR / f"math_failures_{ts}.json"
        log_path.write_text(json.dumps({"run_at": ts, "failures": failed_list}, indent=2))
        print(f"\nFailures saved to {log_path}")

    print(f"\nDone: {passed}/{len(prompts)} verified → {OUT_FILE}")


if __name__ == "__main__":
    main()
