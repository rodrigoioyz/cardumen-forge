"""
Fase 1 - Scraper: Aiken Language Docs
Fuente: https://aiken-lang.org
Salida: data/raw/aiken_docs.json
"""

import json
import time
import httpx
from bs4 import BeautifulSoup
from pathlib import Path
from tqdm import tqdm

BASE_URL = "https://aiken-lang.org"
START_PATHS = [
    "/installation-instructions",
    "/fundamentals/getting-started",
    "/fundamentals/eutxo",
    "/fundamentals/common-design-patterns",
    "/fundamentals/what-i-wish-i-knew",
    "/language-tour/primitive-types",
    "/language-tour/variables-and-constants",
    "/language-tour/functions",
    "/language-tour/custom-types",
    "/language-tour/control-flow",
    "/language-tour/validators",
    "/language-tour/modules",
    "/language-tour/tests",
    "/language-tour/bench",
    "/language-tour/troubleshooting",
    "/example--hello-world/basics",
    "/example--hello-world/end-to-end/mesh",
    "/example--hello-world/end-to-end/pycardano",
    "/example--hello-world/end-to-end/cardano-cli",
    "/example--vesting/mesh",
    "/example--gift-card",
    "/uplc",
    "/uplc/syntax",
    "/uplc/cli",
    "/uplc/builtins",
    "/ecosystem-overview",
    "/glossary",
    "/faq",
]
OUTPUT = Path("data/raw/aiken_docs.json")


def crawl_links(client, start_url, visited):
    """Encuentra links internos del mismo dominio."""
    try:
        resp = client.get(start_url)
        resp.raise_for_status()
    except Exception:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    links = []
    for a in soup.select("a[href]"):
        href = a["href"]
        if href.startswith("/") and "#" not in href:
            full = BASE_URL + href
            if full not in visited:
                links.append(full)
        elif BASE_URL in href and "#" not in href:
            if href not in visited:
                links.append(href)
    return list(dict.fromkeys(links))


def parse_page(url, html):
    soup = BeautifulSoup(html, "html.parser")

    # Título
    title_el = soup.find("h1") or soup.find("title")
    title = title_el.get_text(strip=True) if title_el else url.split("/")[-1]

    # Contenido principal
    main = (
        soup.find("main")
        or soup.find("article")
        or soup.find("div", class_=lambda c: c and "content" in c)
        or soup.find("body")
    )

    if not main:
        return None

    # Extraer secciones con sus encabezados
    sections = []
    current_heading = title
    current_content = []
    current_code = []

    for el in main.find_all(["h1", "h2", "h3", "h4", "p", "li", "pre", "code"]):
        tag = el.name
        if tag in ["h1", "h2", "h3", "h4"]:
            if current_content or current_code:
                sections.append({
                    "heading": current_heading,
                    "content": " ".join(current_content),
                    "code_examples": current_code[:],
                })
            current_heading = el.get_text(strip=True)
            current_content = []
            current_code = []
        elif tag == "pre":
            code = el.get_text(strip=True)
            if code:
                current_code.append(code)
        elif tag == "code" and el.parent.name != "pre":
            pass  # inline code, skip
        else:
            text = el.get_text(separator=" ", strip=True)
            if text:
                current_content.append(text)

    if current_content or current_code:
        sections.append({
            "heading": current_heading,
            "content": " ".join(current_content),
            "code_examples": current_code,
        })

    return {
        "title": title,
        "url": url,
        "sections": sections,
    }


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    visited = set()
    to_visit = [BASE_URL + p for p in START_PATHS]
    all_pages = []

    with httpx.Client(timeout=30, follow_redirects=True) as client:
        with tqdm(desc="Scraping aiken-lang.org") as pbar:
            while to_visit:
                url = to_visit.pop(0)
                if url in visited:
                    continue
                visited.add(url)

                try:
                    resp = client.get(url)
                    resp.raise_for_status()
                    page = parse_page(url, resp.text)
                    if page and page["sections"]:
                        all_pages.append(page)

                    pbar.update(1)
                    pbar.set_postfix({"pages": len(all_pages), "url": url[-40:]})
                    time.sleep(0.4)
                except Exception as e:
                    print(f"\n  ERROR {url}: {e}")

    OUTPUT.write_text(json.dumps(all_pages, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nGuardado: {OUTPUT} ({len(all_pages)} páginas)")


if __name__ == "__main__":
    main()
