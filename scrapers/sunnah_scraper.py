#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import functools
import json
import logging
import os
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

# --- Selenium ---
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.common.exceptions import (
    TimeoutException, WebDriverException, NoSuchElementException
)
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- Optional Parquet ---
try:
    import pandas as pd
    HAS_PANDAS = True
except Exception:
    HAS_PANDAS = False

# -------------------------
# Collections (erweiterbar)
# -------------------------
COLLECTIONS = {
    "muslim": {
        "base_url": "https://sunnah.com/muslim",
        "default_total_volumes": 56
    },
    "bukhari": {
        "base_url": "https://sunnah.com/bukhari",
        "default_total_volumes": 97  # anpassbar; kann via --end überschrieben werden
    },
}

SCHEMA_VERSION = "1.1"

# -------------------------
# Logging
# -------------------------
def setup_logging(verbosity: int):
    level = logging.INFO if verbosity == 0 else logging.DEBUG
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("scrape.log", mode="a", encoding="utf-8")
        ],
    )

# -------------------------
# Retry / Backoff
# -------------------------
def retry(backoff=2.0, tries=3, jitter=True, exceptions=(TimeoutException, WebDriverException)):
    def deco(fn):
        @functools.wraps(fn)
        def wrap(*a, **kw):
            wait = 1.0
            for i in range(tries):
                try:
                    return fn(*a, **kw)
                except exceptions as e:
                    if i == tries - 1:
                        raise
                    sleep_for = wait + (random.random() if jitter else 0)
                    logging.warning(f"Retry {i+1}/{tries-1} after error: {e}. Sleeping {sleep_for:.1f}s")
                    time.sleep(sleep_for)
                    wait *= backoff
        return wrap
    return deco

# -------------------------
# Arabic Normalization
# -------------------------
AR_DIAC = r"[\u064B-\u065F\u0670\u06D6-\u06ED]"

def norm_ar(text: str) -> str:
    if not text:
        return ""
    text = re.sub(AR_DIAC, "", text)
    text = text.replace("ـ", "")  # Tatweel
    text = re.sub(r"\s+", " ", text).strip()
    return text

# -------------------------
# Rawi / Isnād Heuristics
# -------------------------
STOP_PHRASES = [
    "يقول", "قال رسول الله", "سمعت رسول الله", "قال النبي", "يقول النبي",
    "حدثني رسول الله", "صلى الله عليه وسلم", "رسول الله قال", "فقال رسول الله"
]

def extract_isnad_part(arabic_text: str) -> str:
    t = arabic_text or ""
    for phrase in STOP_PHRASES:
        if phrase in t:
            return t.split(phrase)[0].strip()
    return t.strip()

RAWI_STOP = ['رَسُولَ اللَّهِ', 'النبي', 'صلى الله عليه وسلم', 'قال رسول الله']

RAWI_PATTERN = (
    r"(?:حَدَّثَنَا|حَدَّثَنِي|أَخْبَرَنَا|أَخْبَرَنِي|أَنْبَأَنَا|قَالَ|سَمِعْتُ|سَمِعَ|يَقُولُ|عَنْ)\s+([^،:\n\"]+)"
)

def extract_rawis(isnad_text: str) -> List[str]:
    matches = re.findall(RAWI_PATTERN, isnad_text or "")
    cleaned = []
    for m in matches:
        m_norm = re.sub(r"[\s\u200f]+", " ", re.sub(r"[^\u0621-\u064A\s]", "", m)).strip()
        if len(m_norm) > 1 and not any(stop in m_norm for stop in RAWI_STOP):
            cleaned.append(m_norm)
    return cleaned

# -------------------------
# Selenium Driver
# -------------------------
def setup_driver(headless=True, page_load_timeout=45) -> webdriver.Chrome:
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    options.add_experimental_option('excludeSwitches', ['enable-logging'])
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(page_load_timeout)
    return driver

# -------------------------
# Parsing Helpers
# -------------------------
BLOCK_SEL = "div.actualHadithContainer"
AR_SEL    = "div.arabic_hadith_full"
EN_SEL    = "div.english_hadith_full"
REF_SEL   = "div.hadith_reference"
GRADE_SEL = "div.gradings"
NEXT_SEL  = "a[rel='next'], a[href*='?page=']"

def get_text_or_empty(block, selector: str) -> str:
    try:
        el = block.find_element(By.CSS_SELECTOR, selector)
        return el.text.strip()
    except NoSuchElementException:
        return ""

def parse_block(block, collection: str, volume_number: int, idx: int, page_url: str) -> Dict:
    arabic = get_text_or_empty(block, AR_SEL)
    english = get_text_or_empty(block, EN_SEL)
    reference = get_text_or_empty(block, REF_SEL)
    grade = get_text_or_empty(block, GRADE_SEL)

    arabic_norm = norm_ar(arabic)
    isnad = extract_isnad_part(arabic_norm)
    rawis = extract_rawis(isnad)
    rawi_nodes = [{"order": i + 1, "name": n} for i, n in enumerate(rawis)]
    rawi_edges = [{"from": rawis[i], "to": rawis[i + 1]} for i in range(len(rawis) - 1)]

    return {
        "id": f"{collection}_{volume_number}_{idx}",
        "collection": collection.capitalize(),
        "volume": volume_number,
        "url": page_url,
        "arabic": arabic,
        "arabic_norm": arabic_norm,
        "english": english,
        "reference": reference,
        "grade": grade,
        "isnad": isnad,
        "rawis": rawi_nodes,
        "rawi_edges": rawi_edges,
        "schema_version": SCHEMA_VERSION
    }

# -------------------------
# Scrape eine Seite (mit optionaler Pagination)
# -------------------------
@retry()
def load_and_collect(driver, url: str, wait_timeout: int) -> List[Dict]:
    out = []
    current_url = url
    while True:
        driver.get(current_url)
        WebDriverWait(driver, wait_timeout).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, BLOCK_SEL))
        )
        blocks = driver.find_elements(By.CSS_SELECTOR, BLOCK_SEL)
        for b in blocks:
            out.append((current_url, b))
        # Pagination
        next_links = driver.find_elements(By.CSS_SELECTOR, NEXT_SEL)
        next_href = None
        for a in next_links:
            try:
                href = a.get_attribute("href") or ""
                if "page=" in href:
                    next_href = href
                    break
            except Exception:
                continue
        if next_href:
            time.sleep(1.5 + random.random())
            current_url = next_href
        else:
            break
    return out

# -------------------------
# Scrape Volume
# -------------------------
def volume_url(base_url: str, volume: int) -> str:
    return f"{base_url}/{volume}"

def ensure_dir(path: str):
    if not os.path.exists(path):
        os.makedirs(path)

def checkpoint_path(dir_: str, collection: str, volume: int) -> str:
    return os.path.join(dir_, f"{collection}_volume_{volume}.json")

def ndjson_path(collection: str) -> str:
    return f"{collection}_full.ndjson"

def json_path(collection: str) -> str:
    return f"{collection}_full.json"

def parquet_path(collection: str) -> str:
    return f"{collection}_full.parquet"

def manifest_path() -> str:
    return "manifest.json"

def load_manifest() -> Dict:
    if os.path.exists(manifest_path()):
        with open(manifest_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    return {"volumes": {}}

def save_manifest(m: Dict):
    with open(manifest_path(), "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=2)

def write_ndjson_item(path: str, item: Dict):
    with open(path, "a", encoding="utf-8") as out:
        out.write(json.dumps(item, ensure_ascii=False) + "\n")

def dedup_by_id(items: List[Dict]) -> List[Dict]:
    seen = set()
    out = []
    for it in items:
        if it["id"] in seen:
            continue
        seen.add(it["id"])
        out.append(it)
    return out

def already_done(checkpoint_dir: str, collection: str, volume: int) -> bool:
    return os.path.exists(checkpoint_path(checkpoint_dir, collection, volume))

def collect_existing(checkpoint_dir: str, collection: str, start: int, end: int) -> List[Dict]:
    all_items = []
    for v in range(start, end + 1):
        p = checkpoint_path(checkpoint_dir, collection, v)
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                all_items.extend(json.load(f))
    return all_items

def scrape_volume(collection_key: str, base_url: str, volume_number: int,
                  checkpoint_dir: str, wait_timeout: int, headless: bool,
                  ndjson_file: str) -> List[Dict]:

    driver = setup_driver(headless=headless)
    url = volume_url(base_url, volume_number)
    data: List[Dict] = []
    try:
        page_blocks = load_and_collect(driver, url, wait_timeout)
        for idx, (page_url, block) in enumerate(page_blocks, start=1):
            try:
                item = parse_block(block, collection_key, volume_number, idx, page_url)
                data.append(item)
                # Stream out immediately
                write_ndjson_item(ndjson_file, item)
            except Exception as e:
                logging.warning(f"Block parse error (vol {volume_number}, idx {idx}): {e}")
        # small politeness delay
        time.sleep(1.0 + random.random())
    except Exception as e:
        logging.error(f"Volume error {volume_number}: {e}")
    finally:
        driver.quit()

    # Save checkpoint
    ensure_dir(checkpoint_dir)
    cp = checkpoint_path(checkpoint_dir, collection_key, volume_number)
    with open(cp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return data

# -------------------------
# Orchestrierung
# -------------------------
def scrape_all(collection_key: str, start: int, end: int, max_workers: int,
               wait_timeout: int, headless: bool, checkpoint_dir: str,
               make_parquet: bool):

    meta = COLLECTIONS[collection_key]
    base_url = meta["base_url"]

    ensure_dir(checkpoint_dir)

    ndjson_file = ndjson_path(collection_key)
    # Wenn neu starten: alte NDJSON ggf. löschen (nur wenn kompletter Bereich neu)
    # Hier konservativ: immer append, weil wir deduplizieren am Ende.

    manifest = load_manifest()
    manifest["collection"] = collection_key
    manifest["volumes"] = manifest.get("volumes", {})

    # Skip bereits vorhandene Volumes
    volumes_to_do = []
    for v in range(start, end + 1):
        if already_done(checkpoint_dir, collection_key, v):
            logging.info(f"[Resume] Skip volume {v} (checkpoint exists)")
        else:
            volumes_to_do.append(v)

    all_items: List[Dict] = []
    # Vorab: lade vorhandene Checkpoints in den RAM (für finales JSON/Parquet)
    all_items.extend(collect_existing(checkpoint_dir, collection_key, start, end))

    if volumes_to_do:
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futs = {
                ex.submit(
                    scrape_volume, collection_key, base_url, v,
                    checkpoint_dir, wait_timeout, headless, ndjson_file
                ): v for v in volumes_to_do
            }
            for fut in as_completed(futs):
                v = futs[fut]
                try:
                    vol_items = fut.result()
                    all_items.extend(vol_items)
                    manifest["volumes"][str(v)] = {
                        "count": len(vol_items),
                        "status": "done",
                        "ts": int(time.time())
                    }
                    save_manifest(manifest)
                    logging.info(f"✅ Volume {v} done, +{len(vol_items)} items (total {len(all_items)})")
                except Exception as e:
                    manifest["volumes"][str(v)] = {
                        "count": 0,
                        "status": f"error: {e}",
                        "ts": int(time.time())
                    }
                    save_manifest(manifest)
                    logging.error(f"❌ Volume {v} failed: {e}")
                time.sleep(1.0 + random.random())

    # Dedup + persist as JSON
    all_items = dedup_by_id(all_items)
    with open(json_path(collection_key), "w", encoding="utf-8") as f:
        json.dump(all_items, f, ensure_ascii=False, indent=2)

    # Optional Parquet
    if make_parquet and HAS_PANDAS:
        try:
            df = pd.DataFrame(all_items)
            df.to_parquet(parquet_path(collection_key), index=False)
            logging.info(f"Parquet written: {parquet_path(collection_key)}")
        except Exception as e:
            logging.warning(f"Parquet write failed: {e}")
    elif make_parquet and not HAS_PANDAS:
        logging.warning("pandas nicht installiert – Parquet wird übersprungen.")

    logging.info(f"🏁 Fertig. {len(all_items)} Hadithe gespeichert → {json_path(collection_key)} & {ndjson_file}")

# -------------------------
# CLI
# -------------------------
def parse_args():
    p = argparse.ArgumentParser(
        description="Sunnah.com Scraper (Muslim/Bukhari) – Selenium-basiert, robust & resume-fähig"
    )
    p.add_argument("--collection", choices=COLLECTIONS.keys(), required=True,
                   help="Welche Sammlung soll gescraped werden (z. B. muslim, bukhari)?")
    p.add_argument("--start", type=int, default=1, help="Startband (inklusive).")
    p.add_argument("--end", type=int, default=None, help="Endband (inklusive).")
    p.add_argument("--max-workers", type=int, default=3, help="Parallelität (Selenium ist schwergewichtig).")
    p.add_argument("--wait-timeout", type=int, default=25, help="Wartezeit für Selektoren (Sek.).")
    p.add_argument("--headless", action="store_true", default=True, help="Headless-Browser nutzen (default true).")
    p.add_argument("--no-headless", dest="headless", action="store_false", help="Headless deaktivieren.")
    p.add_argument("--checkpoint-dir", default="checkpoints", help="Verzeichnis für Band-Checkpoints.")
    p.add_argument("--parquet", action="store_true", help="Zusätzlich Parquet-Datei schreiben (pandas nötig).")
    p.add_argument("-v", "--verbose", action="count", default=0, help="Mehr Logs (ein-/zweimal -v).")
    return p.parse_args()

def main():
    args = parse_args()
    setup_logging(args.verbose)

    if args.collection not in COLLECTIONS:
        logging.error(f"Unbekannte Sammlung: {args.collection}")
        sys.exit(1)

    meta = COLLECTIONS[args.collection]
    if args.end is None:
        args.end = meta["default_total_volumes"]
        logging.info(f"--end nicht gesetzt, verwende Default für {args.collection}: {args.end}")

    if args.start > args.end:
        logging.error("--start darf nicht größer als --end sein.")
        sys.exit(1)

    logging.info(f"🔥 Start: collection={args.collection}, range={args.start}-{args.end}, "
                 f"workers={args.max_workers}, headless={args.headless}")

    scrape_all(
        collection_key=args.collection,
        start=args.start,
        end=args.end,
        max_workers=args.max_workers,
        wait_timeout=args.wait_timeout,
        headless=args.headless,
        checkpoint_dir=args.checkpoint_dir,
        make_parquet=args.parquet
    )

if __name__ == "__main__":
    main()
