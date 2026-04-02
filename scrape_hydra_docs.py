"""
Fase 1 - Scraper: Hydra Head Protocol Docs
Fuente: https://hydra.family/head-protocol/docs
Salida: data/raw/hydra_docs.json
"""

import json
import time
import httpx
from bs4 import BeautifulSoup
from pathlib import Path
from tqdm import tqdm

BASE_URL = "https://hydra.family"
DOCS_ROOT = "https://hydra.family/head-protocol/docs"
OUTPUT = Path("data/raw/hydra_docs.json")


def get_all_doc_links(client):
    """Extrae todos los links del sidebar de Docusaurus."""
    resp = client.get(DOCS_ROOT)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    links = set()
    links.add(DOCS_ROOT)

    # Docusaurus sidebar
    for a in soup.select("nav a[href], .menu a[href], aside a[href]"):
        href = a["href"]
        if href.startswith("/head-protocol"):
            links.add(BASE_URL + href)
        elif href.startswith("http") and "hydra.family" in href:
            links.add(href.split("#")[0])

    # También buscar en el body principal
    for a in soup.select("main a[href]"):
        href = a["href"]
        if href.startswith("/head-protocol/docs"):
            links.add(BASE_URL + href)

    return list(links)


def parse_doc_page(url, html):
    soup = BeautifulSoup(html, "html.parser")

    # Título
    title_el = soup.find("h1")
    title = title_el.get_text(strip=True) if title_el else url.split("/")[-1]

    # Breadcrumb / categoría
    breadcrumb = []
    for el in soup.select(".breadcrumbs__item, nav[aria-label='breadcrumb'] li"):
        text = el.get_text(strip=True)
        if text:
            breadcrumb.append(text)

    # Contenido del artículo
    article = soup.find("article") or soup.find("main") or soup.find("div", class_="markdown")

    if not article:
        return None

    sections = []
    current_heading = title
    current_content = []
    current_code = []

    for el in article.find_all(["h1", "h2", "h3", "h4", "p", "li", "pre", "table"]):
        tag = el.name
        if tag in ["h1", "h2", "h3", "h4"]:
            if current_content or current_code:
                sections.append({
                    "heading": current_heading,
                    "content": " ".join(current_content).strip(),
                    "code_examples": current_code[:],
                })
            current_heading = el.get_text(strip=True)
            current_content = []
            current_code = []
        elif tag == "pre":
            code_el = el.find("code")
            code = code_el.get_text(strip=True) if code_el else el.get_text(strip=True)
            lang_class = ""
            if code_el and code_el.get("class"):
                lang_class = " ".join(code_el["class"])
            if code:
                current_code.append({"lang": lang_class, "code": code})
        elif tag == "table":
            rows = []
            for tr in el.find_all("tr"):
                row = [td.get_text(strip=True) for td in tr.find_all(["th", "td"])]
                if row:
                    rows.append(" | ".join(row))
            if rows:
                current_content.append("\n".join(rows))
        else:
            text = el.get_text(separator=" ", strip=True)
            if text:
                current_content.append(text)

    if current_content or current_code:
        sections.append({
            "heading": current_heading,
            "content": " ".join(current_content).strip(),
            "code_examples": current_code,
        })

    return {
        "title": title,
        "url": url,
        "breadcrumb": breadcrumb,
        "sections": sections,
    }


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    with httpx.Client(timeout=30, follow_redirects=True) as client:
        print("Obteniendo links del sidebar...")
        doc_links = get_all_doc_links(client)
        print(f"  Encontrados {len(doc_links)} links")

        # Segunda pasada: seguir links descubiertos en las páginas
        visited = set()
        to_visit = doc_links[:]
        all_pages = []

        with tqdm(total=len(to_visit), desc="Scraping Hydra docs") as pbar:
            while to_visit:
                url = to_visit.pop(0)
                url = url.split("#")[0]  # strip anchors
                if url in visited:
                    continue
                visited.add(url)

                try:
                    resp = client.get(url)
                    resp.raise_for_status()
                    page = parse_doc_page(url, resp.text)

                    if page and page["sections"]:
                        all_pages.append(page)

                    # Descubrir más links de docs
                    soup = BeautifulSoup(resp.text, "html.parser")
                    for a in soup.select("a[href]"):
                        href = a["href"].split("#")[0]
                        if href.startswith("/head-protocol/docs") and BASE_URL + href not in visited:
                            new_url = BASE_URL + href
                            if new_url not in to_visit:
                                to_visit.append(new_url)
                                pbar.total += 1
                                pbar.refresh()

                    pbar.update(1)
                    pbar.set_postfix({"saved": len(all_pages)})
                    time.sleep(0.4)
                except Exception as e:
                    print(f"\n  ERROR {url}: {e}")
                    pbar.update(1)

    OUTPUT.write_text(json.dumps(all_pages, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nGuardado: {OUTPUT} ({len(all_pages)} páginas)")


if __name__ == "__main__":
    main()
