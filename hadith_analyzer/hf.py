from __future__ import annotations
from pathlib import Path
from dataclasses import dataclass
import json
import re
from typing import List, Dict, Optional, Any

import pandas as pd

try:
    import numpy as np
    from scipy.sparse import load_npz
    from sklearn.metrics.pairwise import cosine_similarity
    HAS_SIM = True
except Exception:
    HAS_SIM = False


@dataclass
class HFPaths:
    root: Path
    meta: Path
    features_dir: Path
    indexes_dir: Path
    hadiths_parquet: Path
    tfidf_matrix: Path
    tfidf_vocab_json: Path
    id_to_row_json: Path

    @classmethod
    def from_root(cls, root: Path) -> "HFPaths":
        return cls(
            root=root,
            meta=root / "meta.json",
            features_dir=root / "features",
            indexes_dir=root / "indexes",
            hadiths_parquet=root / "features" / "hadiths.parquet",
            tfidf_matrix=root / "indexes" / "tfidf_matrix.npz",
            tfidf_vocab_json=root / "indexes" / "tfidf_vocab.json",
            id_to_row_json=root / "indexes" / "id_to_row.json",
        )


class HF:
    """
    HF (Hadith-Fabric) Loader
    -------------------------
    Erwartete Struktur:
      root/
        meta.json
        features/
          hadiths.parquet         # Pflicht
        indexes/                  # Optional (für 'similar')
          tfidf_matrix.npz
          tfidf_vocab.json
          id_to_row.json

    Minimal nutzbar nur mit hadiths.parquet.
    Ähnlichkeitssuche ('similar') funktioniert, wenn TF-IDF-Index vorhanden ist.
    """

    def __init__(self, root: str | Path):
        self.paths = HFPaths.from_root(Path(root))
        if not self.paths.meta.exists():
            raise FileNotFoundError(f"meta.json not found in {self.paths.meta}")
        if not self.paths.hadiths_parquet.exists():
            raise FileNotFoundError(f"hadiths.parquet not found in {self.paths.hadiths_parquet}")

        self.meta: Dict[str, Any] = json.loads(self.paths.meta.read_text(encoding="utf-8"))
        self.hadiths: pd.DataFrame = pd.read_parquet(self.paths.hadiths_parquet)

        # Pflichtspalten prüfen (mindestens diese)
        required_cols = {"id", "collection", "volume", "arabic", "english"}
        missing = required_cols - set(self.hadiths.columns)
        if missing:
            raise ValueError(f"Missing required columns in hadiths.parquet: {missing}")

        # Indexe (optional) – Lazy
        self._tfidf = None          # scipy.sparse.csr_matrix
        self._id_to_row = None      # Dict[str,int]
        self._vocab = None          # Dict[str,int]

    # ------------------------------- #
    # Basics
    # ------------------------------- #
    def get(self, hadith_id: str) -> Optional[Dict[str, Any]]:
        """Hole einen Hadith als Dict (oder None)."""
        rows = self.hadiths[self.hadiths["id"] == hadith_id]
        return rows.iloc[0].to_dict() if len(rows) else None

    def get_many(self, ids: List[str]) -> List[Dict[str, Any]]:
        """Mehrere IDs effizient holen (Ergebnis in gleicher Reihenfolge wie ids)."""
        df = self.hadiths.set_index("id", drop=False)
        out = []
        for _id in ids:
            if _id in df.index:
                out.append(df.loc[_id].to_dict())
        return out

    # ------------------------------- #
    # Suche
    # ------------------------------- #
    def search(self, query: str, lang: str = "both", limit: int = 50, case_sensitive: bool = False) -> List[Dict[str, Any]]:
        """
        Einfache Volltextsuche (Regex-contains) in arabic/english.
        lang: 'arabic' | 'english' | 'both'
        """
        if not query.strip():
            return []

        flags = 0 if case_sensitive else re.IGNORECASE
        pat = re.compile(re.escape(query), flags)

        df = self.hadiths
        mask = False
        if lang in ("arabic", "both"):
            mask = df["arabic"].fillna("").str.contains(pat)
        if lang in ("english", "both"):
            m2 = df["english"].fillna("").str.contains(pat)
            mask = m2 if isinstance(mask, bool) and not mask else (mask | m2)

        res = df[mask].head(limit)
        return res.to_dict(orient="records")

    # ------------------------------- #
    # Ähnlichkeit (TF-IDF)
    # ------------------------------- #
    def similar(self, hadith_id: str, topk: int = 10) -> List[Dict[str, Any]]:
        """
        Top-k ähnliche Hadithe via Cosine-Similarity auf vorab gebauter TF-IDF-Matrix.
        Erfordert:
          indexes/tfidf_matrix.npz (csr_matrix)
          indexes/id_to_row.json   (Map id->row index der Matrix)
        """
        if not HAS_SIM:
            return []

        self._lazy_load_tfidf()
        if self._tfidf is None or self._id_to_row is None:
            return []

        if hadith_id not in self._id_to_row:
            return []

        row_idx = self._id_to_row[hadith_id]
        vec = self._tfidf[row_idx]
        sims = cosine_similarity(vec, self._tfidf).ravel()
        # eigene ID rausfiltern
        sims[row_idx] = -1.0

        # Top-k indices
        top_idx = np.argpartition(sims, -topk)[-topk:]
        # Sortiert absteigend
        top_idx = top_idx[np.argsort(sims[top_idx])[::-1]]

        ids = self._inverse_id_lookup(top_idx)
        scores = sims[top_idx].tolist()
        out = []
        df = self.hadiths.set_index("id", drop=False)
        for _id, score in zip(ids, scores):
            if _id in df.index:
                item = df.loc[_id].to_dict()
                item["_similarity"] = float(score)
                out.append(item)
        return out

    # ------------------------------- #
    # Private Helpers
    # ------------------------------- #
    def _lazy_load_tfidf(self):
        """Lädt TF-IDF-Matrix und Mappings, falls vorhanden (einmalig)."""
        if self._tfidf is not None:
            return
        if not self.paths.tfidf_matrix.exists() or not self.paths.id_to_row_json.exists():
            return
        try:
            self._tfidf = load_npz(self.paths.tfidf_matrix)
            self._id_to_row = json.loads(self.paths.id_to_row_json.read_text(encoding="utf-8"))
            # vocab ist optional
            if self.paths.tfidf_vocab_json.exists():
                self._vocab = json.loads(self.paths.tfidf_vocab_json.read_text(encoding="utf-8"))
        except Exception:
            # Fallback: Indizes ignorieren
            self._tfidf = None
            self._id_to_row = None
            self._vocab = None

    def _inverse_id_lookup(self, row_indices: List[int]) -> List[str]:
        """Rekonstruiere IDs aus row indices (invertiere id_to_row)."""
        id_to_row = self._id_to_row or {}
        # schnelle Umkehrung: Array der Länge max(row)+1
        inv = {r: i for i, r in id_to_row.items()}
        return [inv.get(r, None) for r in row_indices]
