"""
Fase 1 - Scraper: Aiken Standard Library
Fuente: https://aiken-lang.github.io/stdlib/
Salida: data/raw/aiken_stdlib.json
"""

import json
import time
import httpx
from bs4 import BeautifulSoup
from pathlib import Path
from tqdm import tqdm

BASE_URL = "https://aiken-lang.github.io/stdlib"
OUTPUT = Path("data/raw/aiken_stdlib.json")


def get_module_links(client):
    resp = client.get(BASE_URL + "/")
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    links = []
    for a in soup.select("a[href]"):
        href = a["href"]
        if href.startswith("/") and not href == "/" and "#" not in href:
            full = BASE_URL + href
            if full not in links:
                links.append(full)
        elif href.startswith("http") and "aiken-lang.github.io/stdlib" in href and "#" not in href:
            if href not in links:
                links.append(href)
    return links


def parse_module_page(url, html):
    soup = BeautifulSoup(html, "html.parser")
    records = []

    # Nombre del módulo desde el título o la URL
    title_el = soup.find("h1")
    module_name = title_el.get_text(strip=True) if title_el else url.split("/")[-1]

    # Descripción del módulo (primer párrafo antes de las funciones)
    module_desc = ""
    intro = soup.find("section", class_="module-doc") or soup.find("div", class_="intro")
    if intro:
        module_desc = intro.get_text(separator=" ", strip=True)

    # Cada función/tipo/constante definida en el módulo
    # La estructura de aiken stdlib usa <section> o <div> con class "definition"
    for section in soup.select("section, .definition, .function, .type-def"):
        name_el = section.find(["h2", "h3", "h4"])
        if not name_el:
            continue

        fn_name = name_el.get_text(strip=True)
        if not fn_name or fn_name == module_name:
            continue

        # Firma / signature
        sig_el = section.find("code") or section.find("pre")
        signature = sig_el.get_text(strip=True) if sig_el else ""

        # Descripción
        desc_parts = []
        for el in section.find_all(["p", "li"]):
            text = el.get_text(separator=" ", strip=True)
            if text and text != signature:
                desc_parts.append(text)
        description = " ".join(desc_parts)

        # Ejemplos de código
        examples = []
        for pre in section.find_all("pre"):
            code = pre.get_text(strip=True)
            if code and code != signature:
                examples.append(code)

        records.append({
            "module": module_name,
            "name": fn_name,
            "signature": signature,
            "description": description,
            "examples": examples,
            "source_url": url,
        })

    # Si no encontró secciones estructuradas, guardar la página completa como contexto
    if not records:
        body = soup.find("main") or soup.find("body")
        text = body.get_text(separator="\n", strip=True) if body else ""
        if text:
            records.append({
                "module": module_name,
                "name": module_name,
                "signature": "",
                "description": text[:3000],
                "examples": [],
                "source_url": url,
            })

    return records


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    with httpx.Client(timeout=30, follow_redirects=True) as client:
        print("Obteniendo índice de módulos...")
        module_links = get_module_links(client)
        print(f"  Encontrados {len(module_links)} links")

        # Agregar la página principal
        all_urls = list(dict.fromkeys([BASE_URL + "/"] + module_links))

        all_records = []
        for url in tqdm(all_urls, desc="Scraping módulos"):
            try:
                resp = client.get(url)
                resp.raise_for_status()
                records = parse_module_page(url, resp.text)
                all_records.extend(records)
                time.sleep(0.3)
            except Exception as e:
                print(f"\n  ERROR {url}: {e}")

    OUTPUT.write_text(json.dumps(all_records, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nGuardado: {OUTPUT} ({len(all_records)} registros)")


if __name__ == "__main__":
    main()
