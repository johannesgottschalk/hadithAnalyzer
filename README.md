Multimodal Hadith Analysis Tool – Python API &amp; Flask web app for exploring Hadith texts with search, isnād/ rāwī graphing, and similarity detection.
=======
# 🕌 Hadith Analyzer

Ein **wissenschaftliches Analyse- und Explorationstool** für Hadith-Texte  
– inspiriert von [Text-Fabric](https://github.com/annotation/text-fabric) –  
mit Python-API (für Jupyter-Notebooks) **und** Flask-Weboberfläche.

## ✨ Features
- 📦 **Read-Only Data Package** (*Hadith-Fabric* / HF)  
  Struktur: `corpus/`, `features/`, `indexes/`, `meta.json`
- 🔍 **Volltextsuche** (Arabisch & Englisch)
- 🧵 **Isnād & Rāwī-Extraktion**
- 📊 **Ähnlichkeitssuche** (TF-IDF, Cosine Similarity)
- 🌐 **Flask-Frontend** für klickbare Exploration
- 📓 **Jupyter-kompatible API** (`HF`-Loader)

---

## 📂 Projektstruktur
```
hadith-analyzer/
├─ app/                  # Flask-App
│  ├─ routes.py
│  ├─ wsgi.py
│  ├─ templates/
│  └─ static/
├─ hadith_analyzer/      # Python-API & Analysefunktionen
│  ├─ hf.py
│  ├─ similarity.py
│  └─ ...
├─ scripts/              # Hilfsskripte (Build, Deploy, Run)
├─ scrapers/             # Scraper für sunnah.com
├─ data/                 # Lokale Datenpakete (nicht im Repo)
├─ notebooks/            # Jupyter-Notebooks
├─ requirements.txt
├─ .gitignore
└─ README.md
```

---

## 🚀 Installation & Setup

### 1. Repository klonen
```bash
git clone https://github.com/<USERNAME>/hadith-analyzer.git
cd hadith-analyzer
```

### 2. Virtuelle Umgebung anlegen
```bash
python -m venv .venv
. .venv/bin/activate       # Linux/Mac
.venv\Scripts\Activate     # Windows
```

### 3. Abhängigkeiten installieren
```bash
pip install --upgrade pip wheel
pip install -r requirements.txt
```

---

## 🏗️ Datenpaket bauen (HF)

1. **Hadith-Daten scrapen** (Muslim/Bukhari):
```bash
python scrapers/sunnah_scraper.py --collection muslim --parquet
python scrapers/sunnah_scraper.py --collection bukhari --parquet
```

2. **HF-Datenpaket erstellen**:
```bash
python scripts/build_hf.py --input data/raw --out data/hf-2025.08
```

---

## 🖥️ Flask-App starten

### Lokal
```bash
# Linux/Mac
export APP_DATA_DIR=$(pwd)/data/hf-2025.08
export FLASK_SECRET=dev
flask --app app/wsgi.py run

# Windows (PowerShell)
$env:APP_DATA_DIR = "$(Get-Location)\data\hf-2025.08"
$env:FLASK_SECRET = "dev"
flask --app app/wsgi.py run
```
→ Öffne: http://127.0.0.1:5000

---

## 📓 Python-API im Notebook nutzen
```python
from hadith_analyzer.hf import HF
hf = HF("data/hf-2025.08")

# Einzelner Hadith
print(hf.get("muslim_12_34"))

# Suche
hits = hf.search("mercy", lang="english", limit=5)
for h in hits:
    print(h["id"], h["english"])

# Ähnliche Hadithe
similar = hf.similar("muslim_12_34", topk=5)
```

---

## 🌐 Deployment auf Uberspace
- Code (`app/`, `hadith_analyzer/`, `requirements.txt`) + fertiges Datenpaket hochladen
- Gunicorn als Service starten:
```bash
gunicorn -w 2 -b 127.0.0.1:8000 app.wsgi:app
```
- Reverse Proxy auf Port `8000` setzen

---

## 📜 Lizenz
MIT License – siehe [LICENSE](LICENSE).

---

## 🤝 Mitwirken
Pull Requests, Issues & Feedback willkommen!  
Bitte **keine großen Datendateien** ins Repo committen (siehe `.gitignore`).

---

## 📬 Kontakt
Projekt von **Johannes Gottschalk**  
📧 johannes.gottschalk1984@gmail.com