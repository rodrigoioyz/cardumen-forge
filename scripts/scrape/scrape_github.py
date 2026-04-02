"""
Fase 1 - Scraper: GitHub (CIPs + Aiken Design Patterns + Hydra Plutus)
Usa GitHub API via PyGithub.

Salidas:
  data/raw/cips.json
  data/raw/aiken_design_patterns.json
  data/raw/hydra_plutus.json
"""

import json
import os
import base64
import time
from pathlib import Path
from tqdm import tqdm
from github import Github, Auth, GithubException

TOKEN = os.environ.get("GITHUB_TOKEN")
if not TOKEN:
    raise SystemExit("ERROR: Setea GITHUB_TOKEN antes de correr este script.")

g = Github(auth=Auth.Token(TOKEN))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def decode_content(content_file):
    """Decodifica contenido base64 de la API de GitHub."""
    return base64.b64decode(content_file.content).decode("utf-8", errors="replace")


def get_file_text(repo, path):
    try:
        f = repo.get_contents(path)
        return decode_content(f)
    except GithubException:
        return None


def rate_limit_wait(g, min_remaining=50):
    remaining, limit = g.rate_limiting
    if remaining < min_remaining:
        reset_ts = g.rate_limiting_resettime
        import time as t
        wait = max(0, reset_ts - t.time()) + 5
        print(f"\n  Rate limit bajo ({remaining}/{limit}), esperando {wait:.0f}s...")
        t.sleep(wait)


# ---------------------------------------------------------------------------
# CIPs
# ---------------------------------------------------------------------------

ACTIVE_STATUSES = {"Active", "Proposed", "Accepted", "Draft", "Last Check"}
# CIPs de alto valor para desarrollo de contratos
HIGH_VALUE_CIPS = {
    "CIP-0001", "CIP-0002", "CIP-0003",  # fundacionales
    "CIP-0005", "CIP-0010",              # metadata
    "CIP-0025", "CIP-0026", "CIP-0027",  # NFT standards
    "CIP-0030",                          # wallet connector
    "CIP-0054",                          # Plutus smart contracts
    "CIP-0057",                          # Plutus blueprint
    "CIP-0067", "CIP-0068",             # token standards
    "CIP-0069",                          # script credential
    "CIP-0071", "CIP-0072",             # NFT advanced
    "CIP-0085",                          # Plutus v3
    "CIP-0086",                          # transaction metadata
    "CIP-0094",                          # governance
    "CIP-0100", "CIP-0108", "CIP-0116", # Conway era
}


def scrape_cips():
    print("\n=== Scraping CIPs ===")
    output = Path("data/raw/cips.json")
    output.parent.mkdir(parents=True, exist_ok=True)

    repo = g.get_repo("cardano-foundation/CIPs")
    contents = repo.get_contents("")

    # Encontrar todos los directorios CIP-XXXX y CPS-XXXX
    cip_dirs = []
    for item in contents:
        if item.type == "dir" and (item.name.startswith("CIP-") or item.name.startswith("CPS-")):
            cip_dirs.append(item)

    print(f"  Encontrados {len(cip_dirs)} directorios CIP/CPS")

    records = []
    skipped = 0

    for cip_dir in tqdm(cip_dirs, desc="CIPs"):
        rate_limit_wait(g)
        cip_id = cip_dir.name

        try:
            dir_contents = repo.get_contents(cip_dir.path)
        except GithubException as e:
            print(f"\n  ERROR al leer {cip_id}: {e}")
            continue

        # Buscar el README principal
        readme_text = None
        for f in dir_contents:
            if f.name.upper() in ("README.MD", "CIP.MD") or f.name.lower() == "readme.md":
                readme_text = decode_content(f)
                break

        if not readme_text:
            skipped += 1
            continue

        # Parsear frontmatter básico del markdown (CIPs usan YAML frontmatter)
        status = "Unknown"
        title = cip_id
        category = ""

        lines = readme_text.split("\n")
        in_frontmatter = False
        frontmatter_end = 0

        for i, line in enumerate(lines):
            if i == 0 and line.strip() == "---":
                in_frontmatter = True
                continue
            if in_frontmatter:
                if line.strip() == "---":
                    in_frontmatter = False
                    frontmatter_end = i
                    break
                if line.lower().startswith("status:"):
                    status = line.split(":", 1)[1].strip()
                elif line.lower().startswith("title:"):
                    title = line.split(":", 1)[1].strip()
                elif line.lower().startswith("category:"):
                    category = line.split(":", 1)[1].strip()

        # Filtrar por status
        is_high_value = cip_id in HIGH_VALUE_CIPS
        status_ok = any(s.lower() in status.lower() for s in ACTIVE_STATUSES)

        if not is_high_value and not status_ok:
            skipped += 1
            continue

        # Contenido sin frontmatter
        body = "\n".join(lines[frontmatter_end + 1:]).strip() if frontmatter_end > 0 else readme_text

        records.append({
            "id": cip_id,
            "title": title,
            "status": status,
            "category": category,
            "content": body,
            "is_high_value": is_high_value,
            "source_url": f"https://github.com/cardano-foundation/CIPs/tree/master/{cip_id}",
        })

        time.sleep(0.2)

    output.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nGuardado: {output} ({len(records)} CIPs, {skipped} skipped)")


# ---------------------------------------------------------------------------
# Aiken Design Patterns
# ---------------------------------------------------------------------------

def scrape_aiken_patterns():
    print("\n=== Scraping Aiken Design Patterns ===")
    output = Path("data/raw/aiken_design_patterns.json")

    repo = g.get_repo("Anastasia-Labs/aiken-design-patterns")
    records = []

    # README principal
    readme = get_file_text(repo, "README.md")
    if readme:
        records.append({
            "type": "readme",
            "name": "Aiken Design Patterns - Overview",
            "content": readme,
            "source_url": "https://github.com/Anastasia-Labs/aiken-design-patterns",
        })

    # Buscar archivos .ak en el repo
    def walk_dir(path=""):
        rate_limit_wait(g)
        try:
            items = repo.get_contents(path)
        except GithubException:
            return
        for item in items:
            if item.type == "dir":
                walk_dir(item.path)
            elif item.name.endswith(".ak"):
                code = decode_content(item)
                records.append({
                    "type": "aiken_source",
                    "name": item.path,
                    "content": code,
                    "source_url": f"https://github.com/Anastasia-Labs/aiken-design-patterns/blob/main/{item.path}",
                })
            elif item.name.lower() == "readme.md" and path != "":
                text = decode_content(item)
                records.append({
                    "type": "pattern_doc",
                    "name": path + "/README.md",
                    "content": text,
                    "source_url": f"https://github.com/Anastasia-Labs/aiken-design-patterns/blob/main/{item.path}",
                })
            time.sleep(0.1)

    print("  Descargando archivos .ak y READMEs...")
    walk_dir()

    output.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Guardado: {output} ({len(records)} archivos)")


# ---------------------------------------------------------------------------
# Hydra Plutus (solo partes relevantes en Haskell/Plutus del repo hydra)
# ---------------------------------------------------------------------------

HYDRA_RELEVANT_PATHS = [
    "hydra-plutus",
    "hydra-cardano-api",
    "docs",          # docs en markdown del repo
]
RELEVANT_EXTENSIONS = {".hs", ".md", ".cabal"}
SKIP_DIRS = {"node_modules", ".git", "dist-newstyle", ".stack-work"}


def scrape_hydra_code():
    print("\n=== Scraping Hydra Plutus / Cardano API ===")
    output = Path("data/raw/hydra_plutus.json")

    repo = g.get_repo("cardano-scaling/hydra")
    records = []

    def walk_path(path):
        rate_limit_wait(g)
        try:
            items = repo.get_contents(path)
        except GithubException as e:
            print(f"  SKIP {path}: {e}")
            return

        for item in tqdm(items, desc=f"  {path}", leave=False):
            if item.type == "dir":
                if item.name not in SKIP_DIRS:
                    walk_path(item.path)
            elif item.type == "file":
                ext = Path(item.name).suffix
                if ext in RELEVANT_EXTENSIONS and item.size < 100_000:  # skip archivos muy grandes
                    code = decode_content(item)
                    records.append({
                        "type": "source" if ext != ".md" else "doc",
                        "path": item.path,
                        "extension": ext,
                        "content": code,
                        "source_url": f"https://github.com/cardano-scaling/hydra/blob/master/{item.path}",
                    })
            time.sleep(0.15)

    for path in HYDRA_RELEVANT_PATHS:
        print(f"\n  Procesando {path}/...")
        walk_path(path)

    output.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nGuardado: {output} ({len(records)} archivos)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    targets = sys.argv[1:] if len(sys.argv) > 1 else ["cips", "patterns", "hydra"]

    if "cips" in targets:
        scrape_cips()
    if "patterns" in targets:
        scrape_aiken_patterns()
    if "hydra" in targets:
        scrape_hydra_code()

    print("\n=== Fase 1 GitHub completa ===")
