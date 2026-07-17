#!/usr/bin/env python3
"""Plot HemaGuide history/query case similarity from Chroma embeddings.

The plotted coordinates are a 2-D UMAP projection.  Top-k labels are ranked
in the original embedding space with cosine similarity, never by 2-D distance.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

import chromadb
import matplotlib.pyplot as plt
import numpy as np

# Allow `python scripts/plot_case_similarity_umap.py ...` from the repository root.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.vectordb import _create_embedding_function


LOGGER = logging.getLogger("plot_case_similarity_umap")
COLORS = {
    "leukemia": "#E45745",
    "lymphoma": "#159A87",
    "unknown": "#8290A6",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a UMAP case-similarity plot from HemaGuide ChromaDB."
    )
    parser.add_argument("--db-path", type=Path, default=Path("kb_storage/chroma_db"))
    parser.add_argument("--collection", default="tumorboards")
    parser.add_argument("--manifest", type=Path, required=True,
                        help="CSV with case_id/group and relative_path or source_file columns")
    parser.add_argument("--query-dir", type=Path, required=True,
                        help="Directory containing extracted query JSON files")
    parser.add_argument("--embedding-model", required=True,
                        help="Exactly the model used to build the Chroma collection")
    parser.add_argument("--embedding-api", default="ollama", choices=["ollama", "openai"])
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--n-neighbors", type=int, default=12)
    parser.add_argument("--min-dist", type=float, default=0.18)
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument("--method", choices=["umap", "pca"], default="umap",
                        help="Use PCA only as an explicit dependency-free fallback")
    parser.add_argument("--output-dir", type=Path, default=Path("results/case_similarity_plot"))
    parser.add_argument("--dpi", type=int, default=300)
    return parser.parse_args()


def normalize_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def case_key_from_source(value: Any) -> str:
    stem = Path(str(value or "")).stem
    return normalize_key(stem)


def load_manifest(path: Path) -> dict[str, dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"Manifest is empty: {path}")

    index: dict[str, dict[str, str]] = {}
    for row in rows:
        group = str(row.get("group", "unknown")).lower()
        if group not in COLORS:
            group = "unknown"
        keys = [
            row.get("case_id", ""),
            row.get("patient_id", ""),
            row.get("source_file", ""),
            row.get("relative_path", ""),
        ]
        for key in keys:
            if key:
                index[normalize_key(key)] = {"case_id": row.get("case_id", "") or Path(str(key)).stem,
                                             "group": group}
                index[case_key_from_source(key)] = index[normalize_key(key)]
    return index


def infer_case_info(metadata: dict[str, Any], manifest: dict[str, dict[str, str]]) -> dict[str, str]:
    candidates = [
        metadata.get("source_file", ""),
        metadata.get("patient_id", ""),
        metadata.get("document_id", ""),
    ]
    for candidate in candidates:
        key = normalize_key(candidate)
        if key in manifest:
            return manifest[key]
        key = case_key_from_source(candidate)
        if key in manifest:
            return manifest[key]

    text = " ".join(str(metadata.get(field, "")) for field in ("entity_slug", "main_diagnosis"))
    group = infer_group(text)
    return {"case_id": str(metadata.get("document_id", "unknown")), "group": group}


def infer_group(text: str) -> str:
    lowered = text.lower()
    return "lymphoma" if any(token in lowered for token in ("lymphoma", "lymphom", "淋巴瘤")) else "leukemia" if any(
        token in lowered for token in ("leukemia", "leukaemia", "aml", "all", "cml", "mye", "白血病")) else "unknown"


def load_history_embeddings(collection: Any, manifest: dict[str, dict[str, str]]) -> tuple[np.ndarray, list[dict[str, Any]]]:
    result = collection.get(where={"section": "history"}, include=["embeddings", "metadatas", "documents"])
    embeddings = np.asarray(result.get("embeddings", []), dtype=np.float32)
    metadatas = result.get("metadatas", []) or []
    if embeddings.ndim != 2 or len(embeddings) == 0:
        raise RuntimeError("No history embeddings found. Rebuild the knowledge base first.")
    if len(metadatas) != len(embeddings):
        raise RuntimeError("Chroma returned mismatched history embeddings and metadata.")

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    keep: list[int] = []
    for index, metadata in enumerate(metadatas):
        info = infer_case_info(metadata or {}, manifest)
        case_id = info["case_id"]
        if case_id in seen:
            continue
        seen.add(case_id)
        keep.append(index)
        rows.append({
            "case_id": case_id,
            "group": info["group"],
            "role": "history",
            "source_file": metadata.get("source_file", "") if metadata else "",
            "main_diagnosis": metadata.get("main_diagnosis", "") if metadata else "",
        })
    return embeddings[keep], rows


def query_text(document: dict[str, Any]) -> str:
    sections = document.get("sections", document)
    history = str(sections.get("history", "") or "").strip()
    if history and history.lower() not in {"nicht vorhanden", "keine"}:
        return history
    fields = ("main_diagnosis", "predictive_factors", "prior_treatments", "question")
    return "\n".join(str(sections.get(field, "") or "") for field in fields).strip()


def load_queries(query_dir: Path, manifest: dict[str, dict[str, str]]) -> list[dict[str, Any]]:
    queries = []
    for path in sorted(query_dir.glob("*.json")):
        with path.open("r", encoding="utf-8") as handle:
            document = json.load(handle)
        sections = document.get("sections", document)
        text = query_text(document)
        if not text:
            LOGGER.warning("Skipping query without usable text: %s", path)
            continue
        source = document.get("source_file", path.name)
        source_key = normalize_key(source)
        manifest_info = manifest.get(source_key) or manifest.get(case_key_from_source(source))
        group = manifest_info["group"] if manifest_info else infer_group(
            " ".join(str(sections.get(field, "") or "") for field in ("entity", "main_diagnosis"))
        )
        queries.append({
            "case_id": Path(str(source)).stem,
            "group": group,
            "role": "query",
            "source_file": str(source),
            "text": text,
        })
    if not queries:
        raise RuntimeError(f"No usable query JSON files found in {query_dir}")
    return queries


def cosine_scores(matrix: np.ndarray, vector: np.ndarray) -> np.ndarray:
    matrix_norm = matrix / np.maximum(np.linalg.norm(matrix, axis=1, keepdims=True), 1e-12)
    vector_norm = vector / max(float(np.linalg.norm(vector)), 1e-12)
    return matrix_norm @ vector_norm


def reduce_embeddings(embeddings: np.ndarray, args: argparse.Namespace) -> tuple[np.ndarray, str]:
    if args.method == "pca":
        centered = embeddings - embeddings.mean(axis=0, keepdims=True)
        _, _, vh = np.linalg.svd(centered, full_matrices=False)
        return centered @ vh[:2].T, "PCA"
    try:
        import umap
    except ImportError as exc:
        raise RuntimeError("UMAP is not installed. Run `pip install umap-learn` or use --method pca.") from exc
    n_neighbors = min(max(2, args.n_neighbors), len(embeddings) - 1)
    reducer = umap.UMAP(
        n_components=2,
        metric="cosine",
        n_neighbors=n_neighbors,
        min_dist=args.min_dist,
        random_state=args.random_state,
        transform_seed=args.random_state,
        n_jobs=1,
    )
    return reducer.fit_transform(embeddings), "UMAP"


def convex_hull(points: np.ndarray) -> np.ndarray:
    if len(points) < 3:
        return points
    ordered = sorted(map(tuple, points))

    def cross(o: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for point in ordered:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper: list[tuple[float, float]] = []
    for point in reversed(ordered):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return np.asarray(lower[:-1] + upper[:-1], dtype=float)


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if args.top_k < 1:
        raise ValueError("--top-k must be positive")

    manifest = load_manifest(args.manifest)
    client = chromadb.PersistentClient(path=str(args.db_path))
    collection = client.get_collection(args.collection)
    history_embeddings, history_rows = load_history_embeddings(collection, manifest)
    queries = load_queries(args.query_dir, manifest)

    embedding_function = _create_embedding_function(args.embedding_model, "ollama" if args.embedding_api == "ollama" else None)
    query_embeddings = np.asarray(embedding_function([query["text"] for query in queries]), dtype=np.float32)
    if query_embeddings.shape[1] != history_embeddings.shape[1]:
        raise RuntimeError(
            f"Embedding dimension mismatch: history={history_embeddings.shape[1]}, queries={query_embeddings.shape[1]}. "
            "Use the same embedding model used to build ChromaDB."
        )

    all_embeddings = np.vstack([history_embeddings, query_embeddings])
    coordinates, method_name = reduce_embeddings(all_embeddings, args)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    coordinate_rows: list[dict[str, Any]] = []
    history_coords = coordinates[:len(history_rows)]
    query_coords = coordinates[len(history_rows):]
    for row, coordinate in zip(history_rows, history_coords):
        coordinate_rows.append({**{key: row.get(key, "") for key in ("case_id", "group", "role", "source_file", "main_diagnosis")},
                                "x": f"{coordinate[0]:.8f}", "y": f"{coordinate[1]:.8f}",
                                "nearest_rank": "", "similarity_score": "", "nearest_cases": ""})

    query_rankings: dict[str, list[tuple[str, float]]] = {}
    for query, query_vector, coordinate in zip(queries, query_embeddings, query_coords):
        scores = cosine_scores(history_embeddings, query_vector)
        eligible = np.arange(len(history_rows))
        if query["group"] in COLORS and query["group"] != "unknown":
            grouped = np.asarray([row["group"] == query["group"] for row in history_rows])
            if grouped.any():
                eligible = eligible[grouped]
        ranked = eligible[np.argsort(scores[eligible])[::-1]][:args.top_k]
        ranking = [(history_rows[index]["case_id"], float(scores[index])) for index in ranked]
        query_rankings[query["case_id"]] = ranking
        labels = "; ".join(f"{rank + 1}:{case_id}:{score:.3f}" for rank, (case_id, score) in enumerate(ranking))
        coordinate_rows.append({"case_id": query["case_id"], "group": query["group"], "role": "query",
                                "source_file": query["source_file"], "main_diagnosis": "",
                                "x": f"{coordinate[0]:.8f}", "y": f"{coordinate[1]:.8f}",
                                "nearest_rank": "C", "similarity_score": "", "nearest_cases": labels})

    coordinate_path = args.output_dir / "case_similarity_coordinates.csv"
    with coordinate_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=coordinate_rows[0].keys())
        writer.writeheader()
        writer.writerows(coordinate_rows)

    # Produce one figure per disease group so their distributions are not visually
    # compressed or mistaken for overlapping clusters. Coordinates and rankings
    # remain shared and are still computed from the original embedding space.
    for plot_group in ("leukemia", "lymphoma"):
        indices = [i for i, row in enumerate(history_rows) if row["group"] == plot_group]
        group_queries = [(query, coordinate) for query, coordinate in zip(queries, query_coords)
                         if query["group"] == plot_group]
        if not indices and not group_queries:
            continue
        fig, ax = plt.subplots(figsize=(10, 8), dpi=args.dpi)
        points = history_coords[indices]
        color = COLORS[plot_group]
        if len(points):
            label = "Leukemia" if plot_group == "leukemia" else "Lymphoma"
            ax.scatter(points[:, 0], points[:, 1], s=38, c=color, alpha=0.8, linewidths=0.35,
                       edgecolors="white", label=f"{label} history (n={len(points)})")
            hull = convex_hull(points)
            if len(hull) >= 3:
                closed = np.vstack([hull, hull[0]])
                ax.plot(closed[:, 0], closed[:, 1], color=color, linewidth=1.1,
                        linestyle=(0, (5, 4)), alpha=0.6)
        for query, coordinate in group_queries:
            ax.scatter([coordinate[0]], [coordinate[1]], s=190, marker="s", c=[color],
                       edgecolors="#1D2939", linewidths=1.8, zorder=6)
            ax.text(coordinate[0], coordinate[1], "C", color="white", ha="center", va="center",
                    fontsize=9, fontweight="bold", zorder=7)
            for rank, (case_id, _score) in enumerate(query_rankings[query["case_id"]], start=1):
                index = next(i for i, row in enumerate(history_rows) if row["case_id"] == case_id)
                point = history_coords[index]
                ax.annotate(str(rank), xy=point, xytext=(5, 5), textcoords="offset points",
                            fontsize=9, color="#25364D", fontweight="bold", zorder=7,
                            bbox={"boxstyle": "circle,pad=0.18", "fc": "#D9E7F3",
                                  "ec": "#25364D", "lw": 0.8})
        label = "Leukemia" if plot_group == "leukemia" else "Lymphoma"
        ax.set_title(f"Clinical case similarity search — {label}", fontsize=17, pad=16, color="#25364D")
        ax.text(0.5, 1.01, f"{method_name} projection; Top-{args.top_k} ranked in original embedding space",
                transform=ax.transAxes, ha="center", va="bottom", fontsize=9.5, color="#5B677A")
        ax.set_xlabel(f"{method_name}-1")
        ax.set_ylabel(f"{method_name}-2")
        ax.grid(True, color="#D9E0E8", linewidth=0.6, alpha=0.7)
        ax.set_facecolor("#FCFDFE")
        ax.legend(frameon=False, loc="best")
        fig.tight_layout()
        stem = f"case_similarity_{plot_group}"
        fig.savefig(args.output_dir / f"{stem}.png", dpi=args.dpi, bbox_inches="tight")
        fig.savefig(args.output_dir / f"{stem}.svg", bbox_inches="tight")
        plt.close(fig)
        LOGGER.info("Wrote %s", args.output_dir / f"{stem}.png")
    LOGGER.info("Wrote %s", coordinate_path)
    for query_id, ranking in query_rankings.items():
        LOGGER.info("%s Top-%d: %s", query_id, args.top_k,
                    ", ".join(f"{case}:{score:.3f}" for case, score in ranking))


if __name__ == "__main__":
    main()
