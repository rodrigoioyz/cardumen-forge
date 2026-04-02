"""
Fase 1 - Scraper alternativo: Aiken stdlib via GitHub repo
Fuente: https://github.com/aiken-lang/stdlib
Salida: data/raw/aiken_stdlib.json (reemplaza el anterior)

El repo tiene los módulos en /lib/aiken/ como archivos .ak
con comentarios de documentación inline.
"""

import json
import os
import time
from pathlib import Path
from tqdm import tqdm
from github import Github, Auth, GithubException
import base64

TOKEN = os.environ.get("GITHUB_TOKEN")
if not TOKEN:
    raise SystemExit("ERROR: Setea GITHUB_TOKEN antes de correr este script.")

g = Github(auth=Auth.Token(TOKEN))
OUTPUT = Path("data/raw/aiken_stdlib.json")


def decode_content(content_file):
    return base64.b64decode(content_file.content).decode("utf-8", errors="replace")


def rate_limit_wait(min_remaining=50):
    remaining, limit = g.rate_limiting
    if remaining < min_remaining:
        reset_ts = g.rate_limiting_resettime
        import time as t
        wait = max(0, reset_ts - t.time()) + 5
        print(f"\n  Rate limit bajo ({remaining}/{limit}), esperando {wait:.0f}s...")
        t.sleep(wait)


def parse_aiken_module(path, source_code):
    """
    Parsea un archivo .ak extrayendo funciones/tipos con sus doc-comments.
    Doc-comments en Aiken usan /// para documentar el item siguiente.
    """
    module_name = path.replace("lib/", "").replace("/", ".").replace(".ak", "")
    records = []

    lines = source_code.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i]

        # Acumular doc-comments (///)
        if line.strip().startswith("///"):
            doc_lines = []
            while i < len(lines) and lines[i].strip().startswith("///"):
                doc_lines.append(lines[i].strip().lstrip("///").strip())
                i += 1

            # El siguiente item no-vacío es la definición
            while i < len(lines) and lines[i].strip() == "":
                i += 1

            if i < len(lines):
                definition_line = lines[i].strip()
                # Capturar toda la definición hasta el primer {
                def_lines = []
                j = i
                while j < len(lines):
                    def_lines.append(lines[j])
                    if "{" in lines[j] or lines[j].strip().endswith("}"):
                        break
                    if j > i + 5:  # máx 6 líneas de firma
                        break
                    j += 1
                signature = " ".join(l.strip() for l in def_lines).split("{")[0].strip()

                # Determinar tipo (fn, type, const, test)
                item_type = "unknown"
                name = ""
                if definition_line.startswith("pub fn ") or definition_line.startswith("fn "):
                    item_type = "function"
                    name = definition_line.split("fn ", 1)[-1].split("(")[0].strip()
                elif definition_line.startswith("pub type ") or definition_line.startswith("type "):
                    item_type = "type"
                    name = definition_line.split("type ", 1)[-1].split("{")[0].strip()
                elif definition_line.startswith("pub const ") or definition_line.startswith("const "):
                    item_type = "constant"
                    name = definition_line.split("const ", 1)[-1].split("=")[0].strip()
                else:
                    name = definition_line[:60]

                description = " ".join(doc_lines)
                if name:
                    records.append({
                        "module": module_name,
                        "name": name,
                        "type": item_type,
                        "signature": signature,
                        "description": description,
                        "source_url": f"https://github.com/aiken-lang/stdlib/blob/main/{path}",
                    })
        else:
            i += 1

    # Si no encontró items documentados, guardar el módulo completo como contexto
    if not records:
        records.append({
            "module": module_name,
            "name": module_name,
            "type": "module",
            "signature": "",
            "description": f"Aiken stdlib module: {module_name}",
            "source_code": source_code[:4000],
            "source_url": f"https://github.com/aiken-lang/stdlib/blob/main/{path}",
        })

    return records


def walk_repo(repo, path="lib"):
    rate_limit_wait()
    try:
        items = repo.get_contents(path)
    except GithubException as e:
        print(f"  SKIP {path}: {e}")
        return []

    files = []
    for item in items:
        if item.type == "dir":
            files.extend(walk_repo(repo, item.path))
        elif item.name.endswith(".ak"):
            files.append(item)
    return files


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    print("Conectando al repo aiken-lang/stdlib...")
    repo = g.get_repo("aiken-lang/stdlib")

    print("Listando archivos .ak en /lib...")
    ak_files = walk_repo(repo, "lib")
    print(f"  Encontrados {len(ak_files)} archivos .ak")

    all_records = []

    for f in tqdm(ak_files, desc="Parseando módulos"):
        rate_limit_wait()
        try:
            source = decode_content(f)
            records = parse_aiken_module(f.path, source)
            all_records.extend(records)
            time.sleep(0.15)
        except Exception as e:
            print(f"\n  ERROR {f.path}: {e}")

    # También bajar el README como contexto general
    try:
        readme = repo.get_contents("README.md")
        readme_text = decode_content(readme)
        all_records.append({
            "module": "README",
            "name": "stdlib overview",
            "type": "overview",
            "signature": "",
            "description": readme_text,
            "source_url": "https://github.com/aiken-lang/stdlib",
        })
    except Exception:
        pass

    OUTPUT.write_text(json.dumps(all_records, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nGuardado: {OUTPUT} ({len(all_records)} registros)")
    print(f"Tamaño: {OUTPUT.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
