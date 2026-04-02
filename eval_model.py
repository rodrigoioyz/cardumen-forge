#!/usr/bin/env python3
"""
eval_model.py
Evalúa un modelo fine-tuneado de Aiken v3 contra una suite de prompts estándar.
Guarda resultados en eval_results/ para comparar versiones.

Configuración via variables de entorno:
    LM_STUDIO_URL   URL base de la API (ej: http://192.168.1.x:1234)
    LM_MODEL_NAME   nombre del modelo en LM Studio (ej: aiken-v3-q4)

Uso:
    LM_STUDIO_URL=http://... LM_MODEL_NAME=my-model .venv/bin/python3 eval_model.py
    LM_STUDIO_URL=http://... LM_MODEL_NAME=my-model .venv/bin/python3 eval_model.py --compare
"""

import os, sys, json, re, argparse
from datetime import datetime
from pathlib import Path
from openai import OpenAI

RESULTS_DIR = Path("eval_results")
SYSTEM_PROMPT = """\
You are an expert Aiken v3 smart contract engineer.
Generate complete, compilable Aiken v3 validators.
Always use slash-style imports (use cardano/assets, not use cardano.assets).
Always wrap handlers inside a validator { } block.
"""

# ─────────────────────────────────────────────────────────────────────────────
# Test suite — prompts diseñados para reproducir fallos del modelo v11
# Cada test tiene: id, prompt, y checks esperados / prohibidos
# ─────────────────────────────────────────────────────────────────────────────
TEST_SUITE = [
    {
        "id": "spend_owner_sig",
        "category": "spend / signature",
        "prompt": "Write an Aiken v3 spend validator that only allows the owner to withdraw funds. The owner's key hash is stored in the datum.",
        "must_contain": ["validator", "spend(", "extra_signatories"],
        "must_not_contain": ["self.signatures", "tx.signatures", "self.time", "use cardano."],
    },
    {
        "id": "spend_ada_payment",
        "category": "spend / ADA",
        "prompt": "Write an Aiken v3 spend validator for a simple escrow: release funds when at least 5 ADA is sent to the beneficiary.",
        "must_contain": ["validator", "spend(", "lovelace_of"],
        "must_not_contain": ["output.assets.ada", "output.value >=", "self.time", "use cardano."],
    },
    {
        "id": "spend_time_lock",
        "category": "spend / time",
        "prompt": "Write an Aiken v3 spend validator that locks funds until a deadline stored in the datum.",
        "must_contain": ["validator", "spend(", "validity_range"],
        "must_not_contain": ["self.time", "block_num", "self.signatures", "use cardano."],
    },
    {
        "id": "spend_nft_gate",
        "category": "spend / NFT",
        "prompt": "Write an Aiken v3 spend validator that only allows spending if the transaction includes a specific NFT.",
        "must_contain": ["validator", "spend(", "has_nft"],
        "must_not_contain": ["self.time", "output.assets.ada", "use cardano."],
    },
    {
        "id": "spend_multisig",
        "category": "spend / multisig",
        "prompt": "Write an Aiken v3 spend validator that requires 2 out of 3 admins to sign the transaction. Admin keys are stored in the datum.",
        "must_contain": ["validator", "spend(", "extra_signatories", "list.count"],
        "must_not_contain": ["MultiSignature", "self.signatures", "use cardano."],
    },
    {
        "id": "mint_nft_one_shot",
        "category": "mint / one-shot",
        "prompt": "Write an Aiken v3 mint validator for a one-shot NFT policy that can only mint once by consuming a specific UTXO.",
        "must_contain": ["validator", "mint(", "policy_id"],
        "must_not_contain": ["self.time", "self.signatures", "use cardano.", "fn spend("],
    },
    {
        "id": "mint_admin_capped",
        "category": "mint / capped supply",
        "prompt": "Write an Aiken v3 mint validator where only an admin can mint, and total supply cannot exceed 1,000,000 tokens.",
        "must_contain": ["validator", "mint(", "extra_signatories", "quantity_of"],
        "must_not_contain": ["self.signatures", "self.time", "use cardano."],
    },
    {
        "id": "withdraw_staking",
        "category": "withdraw",
        "prompt": "Write an Aiken v3 withdraw validator that allows staking rewards to be claimed only by the registered owner.",
        "must_contain": ["validator", "withdraw(", "extra_signatories"],
        "must_not_contain": ["self.signatures", "self.time", "use cardano."],
    },
    {
        "id": "spend_combined",
        "category": "spend / combined",
        "prompt": "Write an Aiken v3 spend validator that checks: the owner signed AND the transaction is submitted before a deadline.",
        "must_contain": ["validator", "spend(", "extra_signatories", "validity_range"],
        "must_not_contain": ["self.signatures", "self.time", "use cardano."],
    },
    {
        "id": "spend_reference_input",
        "category": "spend / reference inputs",
        "prompt": "Write an Aiken v3 spend validator that reads a price from a reference input oracle and checks the payment is at least that price.",
        "must_contain": ["validator", "spend(", "reference_inputs", "find_input"],
        "must_not_contain": ["self.signatures", "self.time", "use cardano."],
    },
    {
        "id": "vote_governance",
        "category": "vote / governance",
        "prompt": "Write an Aiken v3 vote validator for a DAO that only allows a registered committee member to cast a governance vote.",
        "must_contain": ["validator", "vote(", "Voter"],
        "must_not_contain": ["self.signatures", "self.time", "use cardano.", "fn spend("],
    },
    {
        "id": "publish_cert",
        "category": "publish / certificate",
        "prompt": "Write an Aiken v3 publish validator that only allows the owner to register or deregister a staking credential.",
        "must_contain": ["validator", "publish(", "Certificate"],
        "must_not_contain": ["self.signatures", "self.time", "use cardano."],
    },
    {
        "id": "multi_handler",
        "category": "multi-handler",
        "prompt": "Write an Aiken v3 validator with both a spend handler and a mint handler. The spend checks the owner signed, the mint checks a capped supply.",
        "must_contain": ["validator", "spend(", "mint(", "extra_signatories"],
        "must_not_contain": ["self.signatures", "self.time", "use cardano."],
    },
    {
        "id": "import_style",
        "category": "imports",
        "prompt": "Write an Aiken v3 spend validator that checks a signature and an NFT. Show the correct import style.",
        "must_contain": ["use cardano/", "use aiken/", "validator", "spend("],
        "must_not_contain": ["use cardano.", "use aiken.", "self.signatures"],
    },
    {
        "id": "typed_datum",
        "category": "spend / typed datum",
        "prompt": "Write an Aiken v3 spend validator for a vesting contract. Define a custom VestingDatum type with beneficiary and deadline fields.",
        "must_contain": ["validator", "spend(", "VestingDatum", "validity_range"],
        "must_not_contain": ["self.time", "self.signatures", "use cardano."],
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# Checks automáticos
# ─────────────────────────────────────────────────────────────────────────────

def has_complete_handler(output: str) -> bool:
    m = re.search(r'\bvalidator\b[^{]*\{', output)
    if not m:
        return False
    body = output[m.start():]
    return bool(re.search(r'\b(?:fn\s+)?(spend|mint|withdraw|publish|vote|propose)\s*\(', body))


def run_checks(output: str, must_contain: list, must_not_contain: list) -> dict:
    results = {}
    results["has_validator_block"] = "validator" in output
    results["has_complete_handler"] = has_complete_handler(output)
    results["has_slash_imports"] = bool(re.search(r'\buse\s+\w+/', output))
    results["has_dot_imports"] = bool(re.search(r'^use\s+\w+\.', output, re.MULTILINE))
    results["has_markdown_fence"] = output.strip().startswith("```")

    for pattern in must_contain:
        results[f"contains:{pattern}"] = pattern in output
    for pattern in must_not_contain:
        results[f"absent:{pattern}"] = pattern not in output

    # Overall pass: all checks must be True
    results["pass"] = all(results.values())
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Llamada al modelo
# ─────────────────────────────────────────────────────────────────────────────

def call_model(client, model_name: str, prompt: str, temperature: float = 0.1) -> str:
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ],
        temperature=temperature,
        max_tokens=2048,
    )
    return response.choices[0].message.content.strip()


# ─────────────────────────────────────────────────────────────────────────────
# Comparar dos runs
# ─────────────────────────────────────────────────────────────────────────────

def compare_runs(results_dir: Path):
    runs = sorted(results_dir.glob("eval_*.json"))
    if len(runs) < 2:
        print("Se necesitan al menos 2 runs para comparar.")
        return

    print(f"\nComparando {len(runs)} runs:\n")
    summaries = []
    for path in runs:
        data = json.loads(path.read_text(encoding="utf-8"))
        summaries.append({
            "file": path.name,
            "model": data["model"],
            "timestamp": data["timestamp"],
            "pass_rate": data["summary"]["pass_rate"],
            "passed": data["summary"]["passed"],
            "total": data["summary"]["total"],
            "by_category": data["summary"]["by_category"],
        })

    # Header
    print(f"{'Run':<45} {'Model':<30} {'Pass'}")
    print("-" * 90)
    for s in summaries:
        bar = "█" * int(s["pass_rate"] / 5)
        print(f"{s['file']:<45} {s['model']:<30} {s['passed']}/{s['total']} ({s['pass_rate']:.0f}%) {bar}")

    # Delta entre último y penúltimo
    if len(summaries) >= 2:
        prev, curr = summaries[-2], summaries[-1]
        delta = curr["pass_rate"] - prev["pass_rate"]
        sign = "+" if delta >= 0 else ""
        print(f"\nDelta ({prev['model']} → {curr['model']}): {sign}{delta:.1f}%")

        # Por categoría
        all_cats = set(prev["by_category"]) | set(curr["by_category"])
        print(f"\n{'Category':<30} {'Prev':>8} {'Curr':>8} {'Delta':>8}")
        print("-" * 60)
        for cat in sorted(all_cats):
            p = prev["by_category"].get(cat, {})
            c = curr["by_category"].get(cat, {})
            p_rate = p.get("pass_rate", 0)
            c_rate = c.get("pass_rate", 0)
            d = c_rate - p_rate
            sign = "+" if d >= 0 else ""
            flag = " ✅" if d > 0 else (" ❌" if d < 0 else "")
            print(f"  {cat:<28} {p_rate:>7.0f}% {c_rate:>7.0f}% {sign}{d:>6.0f}%{flag}")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--compare",     action="store_true", help="Comparar runs guardados")
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--limit",       type=int, default=0, help="Correr solo N tests")
    args = parser.parse_args()

    RESULTS_DIR.mkdir(exist_ok=True)

    if args.compare:
        compare_runs(RESULTS_DIR)
        return

    # Leer config desde entorno
    base_url   = os.environ.get("LM_STUDIO_URL")
    model_name = os.environ.get("LM_MODEL_NAME", "local-model")

    if not base_url:
        print("ERROR: LM_STUDIO_URL no definida.")
        print("  Ejemplo: export LM_STUDIO_URL=http://192.168.x.x:1234")
        sys.exit(1)

    client = OpenAI(base_url=f"{base_url}/v1", api_key="not-needed")

    tests = TEST_SUITE[:args.limit] if args.limit > 0 else TEST_SUITE
    print(f"Modelo : {model_name}")
    print(f"API    : {base_url}")
    print(f"Tests  : {len(tests)}")
    print(f"Temp   : {args.temperature}")
    print()

    results = []
    passed  = 0

    for i, test in enumerate(tests):
        print(f"[{i+1}/{len(tests)}] {test['id']} ({test['category']})...")
        try:
            output = call_model(client, model_name, test["prompt"], args.temperature)
        except Exception as e:
            print(f"  ERROR: {e}")
            results.append({**test, "output": "", "checks": {}, "error": str(e)})
            continue

        checks = run_checks(output, test["must_contain"], test["must_not_contain"])
        status = "✅ PASS" if checks["pass"] else "❌ FAIL"
        print(f"  {status}")

        # Mostrar qué falló
        if not checks["pass"]:
            failed_checks = [k for k, v in checks.items() if not v and k != "pass"]
            print(f"  Failed: {failed_checks}")

        if checks["pass"]:
            passed += 1

        results.append({
            "id":       test["id"],
            "category": test["category"],
            "prompt":   test["prompt"],
            "output":   output,
            "checks":   checks,
        })

    # Summary por categoría
    by_category = {}
    for r in results:
        cat = r["category"].split(" / ")[0]
        by_category.setdefault(cat, {"passed": 0, "total": 0})
        by_category[cat]["total"] += 1
        if r.get("checks", {}).get("pass"):
            by_category[cat]["passed"] += 1
    for cat in by_category:
        p = by_category[cat]
        p["pass_rate"] = 100 * p["passed"] / max(1, p["total"])

    pass_rate = 100 * passed / max(1, len(tests))
    print(f"\n{'='*50}")
    print(f"  RESULTADO: {passed}/{len(tests)} ({pass_rate:.0f}%)")
    print(f"\n  Por categoría:")
    for cat, s in sorted(by_category.items()):
        bar = "█" * s["passed"] + "░" * (s["total"] - s["passed"])
        print(f"    {cat:<20}: {s['passed']}/{s['total']} {bar}")
    print(f"{'='*50}")

    # Guardar
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path  = RESULTS_DIR / f"eval_{timestamp}_{model_name.replace('/', '_')[:30]}.json"
    payload   = {
        "timestamp":   timestamp,
        "model":       model_name,
        "base_url":    base_url,
        "temperature": args.temperature,
        "summary": {
            "passed":    passed,
            "total":     len(tests),
            "pass_rate": pass_rate,
            "by_category": by_category,
        },
        "results": results,
    }
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n  Guardado: {out_path}")
    print(f"\nPara comparar con runs anteriores:")
    print(f"  .venv/bin/python3 eval_model.py --compare")


if __name__ == "__main__":
    main()
