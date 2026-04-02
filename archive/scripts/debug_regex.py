import json, re

CODE_OLD = re.compile(
    r"\b(write|implement|create|build|generate|make|develop|construct)\b"
    r"(?:\s+\w+){0,3}\s+"
    r"\b(validator|contract|handler|script|policy|fn|function|spend|mint|withdraw)\b"
    r"|"
    r"\b(show|give)\b.{0,30}\b(example|code|validator|implementation)\b"
    r"|"
    r"\b(escribe|implementa|crea|construye|genera|diseña|desarrolla)\b",
    re.IGNORECASE,
)

CODE_NEW = re.compile(
    r"\b(write|implement|create|build|generate|make|develop|construct)\b"
    r"(?:\s+\w+){0,3}\s+"
    r"\b(validator|contract|handler|script|policy|fn|function|spend|mint|withdraw)\b"
    r"|"
    r"\b(show|give)\b.{0,40}\b(validator|contract|handler|spend|mint|withdraw)\b"
    r"|"
    r"\b(escribe|implementa|crea|construye|genera|diseña|desarrolla)\b",
    re.IGNORECASE,
)

records = []
with open("data/processed/dataset_v13_train.jsonl") as f:
    for line in f:
        line = line.strip()
        if line:
            records.append(json.loads(line))

exc = {"correction_set", "cips", "hydra_docs"}

def no_handler(r):
    m = re.search(r"\bvalidator\b[^{]*\{", r.get("output", ""))
    if not m:
        return True
    body = r["output"][m.start():]
    return not bool(re.search(r"\bfn\s+(spend|mint|withdraw)\s*\(", body))

old = [r for r in records if CODE_OLD.search(r.get("instruction","")) and no_handler(r) and r.get("source") not in exc]
new = [r for r in records if CODE_NEW.search(r.get("instruction","")) and no_handler(r) and r.get("source") not in exc]

print("Old regex:", len(old), "incompletos")
print("New regex:", len(new), "incompletos")
print("Falsos positivos eliminados:", len(old) - len(new))

old_set = set(id(r) for r in old)
new_set = set(id(r) for r in new)
removed = [r for r in old if id(r) not in new_set]
print("\nMuestra eliminados (falsos positivos):")
for r in removed[:8]:
    src = r.get("source", "?")
    instr = r.get("instruction", "")[:90]
    print("  [" + src + "] " + instr)

print("\nMuestra que quedan:")
for r in new[:5]:
    src = r.get("source", "?")
    instr = r.get("instruction", "")[:90]
    print("  [" + src + "] " + instr)
