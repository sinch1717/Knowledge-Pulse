"""Run the chunking experiment and write every number the paper needs.

    python -m research.run --sites plausible,fastapi
    python -m research.run --sites plausible,fastapi --sizes 120,220,400
    python -m research.run --sites plausible --chunkers heading,fixed --sizes 220

For every site x chunker x size it chunks the frozen snapshot, embeds locally,
retrieves by exact cosine search and scores every accepted question. No LLM
calls and no Groq quota: only the local embedding model.

Answerable questions are a site's own; unanswerable ones are questions from the
other sites in the run, which the site's docs cannot answer. Those two sets give
the knowledge-gap metrics (AUROC, false and missed gap rates, threshold
transfer), which is where chunking meets the app's confidence signal.

Output, in data/research/results/<timestamp>/:
    summary.json       everything, read by the website's Research page
    retrieval.csv      one row per site x config
    chunk_stats.csv    one row per site x config
    per_question.csv   one row per question x config, for your own analysis
    report.md          paper-ready tables
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import random
import shutil
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from app import embeddings
from app.config import settings
from app.rag.engine import compute_confidence
from research import metrics as M
from research.chunkers import CHUNKERS, ResearchChunk, chunk_site
from research.common import ROOT, Page, load_pages, site_dir

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("research")

CACHE = ROOT / "cache"
RESULTS = ROOT / "results"
TINY_WORDS = 50
BASELINE = "heading"


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

def load_questions(site: str) -> list[dict]:
    path = site_dir(site) / "questions.json"
    if not path.exists():
        raise SystemExit(f"No questions for {site}. Run: python -m research.questions --site {site}")
    all_q = json.loads(path.read_text(encoding="utf-8"))
    return [q for q in all_q if q.get("accepted") is not False]


def question_review_stats(site: str) -> dict:
    all_q = json.loads((site_dir(site) / "questions.json").read_text(encoding="utf-8"))
    reviewed = [q for q in all_q if q.get("accepted") is not None]
    accepted = [q for q in reviewed if q["accepted"]]
    return {
        "generated": len(all_q),
        "reviewed": len(reviewed),
        "accepted_of_reviewed": len(accepted),
        "acceptance_rate": round(len(accepted) / len(reviewed), 3) if reviewed else None,
    }


def embed_cached(texts: list[str]) -> np.ndarray:
    """Embeddings are deterministic, so cache them on the exact text list."""
    key = hashlib.sha1((settings.embedding_model + "\x00" + "\x1f".join(texts)).encode()).hexdigest()
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{key}.npy"
    if path.exists():
        return np.load(path)
    vectors = embeddings.embed(texts)
    np.save(path, vectors)
    return vectors


# ---------------------------------------------------------------------------
# Chunk quality: needs no questions
# ---------------------------------------------------------------------------

def chunk_stats(pages: list[Page], chunks: list[ResearchChunk]) -> dict:
    by_page: dict[str, list[set]] = defaultdict(list)
    for c in chunks:
        by_page[c.url].append(M.shingles(c.text))

    cross, measured = 0, 0
    code_total, code_split = 0, 0
    for page in pages:
        # Which section does each 3-gram belong to?
        section_of: dict[tuple, int] = {}
        section = 0
        code_blocks: list[set] = []
        for block in page.blocks():
            if block.kind == "heading":
                section += 1
                continue
            sh = M.shingles(block.text)
            for s in sh:
                section_of.setdefault(s, section)
            if block.kind == "code" and len(block.text.split()) >= 20:
                code_blocks.append(sh)

        page_chunks = by_page.get(page.url, [])
        for sh in page_chunks:
            counts: dict[int, int] = defaultdict(int)
            for s in sh:
                if s in section_of:
                    counts[section_of[s]] += 1
            total = sum(counts.values())
            if total < 5:
                continue
            measured += 1
            real = [n for n in counts.values() if n >= 3 and n / total >= 0.10]
            cross += len(real) >= 2

        for code in code_blocks:
            code_total += 1
            best = max((M.coverage(code, sh) for sh in page_chunks), default=0.0)
            code_split += best < 0.9

    sizes = [c.word_count for c in chunks]
    return {
        "chunks": len(chunks),
        "words": M.distribution(sizes),
        "tiny_rate": float(np.mean([s < TINY_WORDS for s in sizes])) if sizes else 0.0,
        "cross_section_rate": cross / measured if measured else 0.0,
        "code_blocks": code_total,
        "code_split_rate": code_split / code_total if code_total else None,
    }


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------

def score_config(
    chunks: list[ResearchChunk],
    answerable: list[dict],
    unanswerable: list[dict],
    k: int,
) -> list[dict]:
    chunk_vectors = embed_cached([c.embed_text for c in chunks])
    chunk_sh = [M.shingles(c.text) for c in chunks]
    rows = []
    for q, is_answerable in [(q, True) for q in answerable] + [(q, False) for q in unanswerable]:
        qv = embed_cached([q["question"]])[0]
        sims = chunk_vectors @ qv
        order = np.argsort(-sims)[: max(10, k)]
        top_sims = [float(max(0.0, sims[i])) for i in order[: settings.retrieval_top_k]]
        row = {
            "qid": q["id"],
            "question_site": q["site"],
            "answerable": is_answerable,
            "confidence": compute_confidence(top_sims),
            "top_similarity": top_sims[0] if top_sims else 0.0,
        }
        if is_answerable:
            ranked = [(chunk_sh[i], chunks[i].url, chunks[i].word_count) for i in order]
            row.update(M.retrieval_scores(M.shingles(q["gold_text"]), q["url"], ranked, k))
        rows.append(row)
    return rows


def summarise(rows: list[dict], tau: float) -> dict:
    ans = [r for r in rows if r["answerable"]]
    pos = [r["confidence"] for r in ans]
    neg = [r["confidence"] for r in rows if not r["answerable"]]
    mean = lambda key: float(np.mean([r[key] for r in ans])) if ans else None  # noqa: E731
    return {
        "answerable": len(ans),
        "unanswerable": len(neg),
        "hit1": mean("hit1"),
        "hitk": mean("hitk"),
        "mrr": mean("rr"),
        "recallk": mean("recallk"),
        "page_hitk": mean("page_hitk"),
        "context_words": mean("context_words"),
        "mean_conf_answerable": float(np.mean(pos)) if pos else None,
        "mean_conf_unanswerable": float(np.mean(neg)) if neg else None,
        "auroc": M.auroc(pos, neg),
        "tau": tau,
        **M.gap_rates(pos, neg, tau),
        "best_tau": M.best_threshold(pos, neg),
    }


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def fmt(v, digits=3):
    if v is None:
        return "–"
    if isinstance(v, float):
        return f"{v:.{digits}f}"
    return str(v)


def write_report(out: Path, summary: dict) -> None:
    lines = [f"# Chunking experiment {summary['run_id']}", ""]
    lines += [f"Embedding model: `{summary['embedding_model']}`. k = {summary['k']}. "
              f"Gap threshold τ = {summary['tau']}. Overlap = {summary['overlap']} words. "
              f"A chunk is relevant if it holds ≥{summary['relevance_threshold']:.0%} of the gold passage "
              f"or lies ≥{summary['containment_threshold']:.0%} inside it (word 3-grams).", ""]
    lines += ["## Sites", "", "| Site | Generator | Pages | Words | Crawled | Questions used | Acceptance |",
              "|---|---|---|---|---|---|---|"]
    for s in summary["sites"]:
        r = s["review"]
        acc = f"{r['accepted_of_reviewed']}/{r['reviewed']}" if r["reviewed"] else "not reviewed"
        lines.append(f"| {s['name']} | {s['generator']} | {s['pages']} | {s['words']:,} | {s['crawled_at'][:10]} "
                     f"| {s['questions']} | {acc} |")
    lines += ["", "## Retrieval (answerable questions)", "",
              "| Site | Config | Chunks | Hit@1 | Hit@k | MRR | Recall@k | Page hit@k | Context words |",
              "|---|---|---|---|---|---|---|---|---|"]
    for r in summary["results"]:
        m = r["retrieval"]
        lines.append(f"| {r['site']} | {r['config']} | {r['chunk_stats']['chunks']} | {fmt(m['hit1'])} | {fmt(m['hitk'])} "
                     f"| {fmt(m['mrr'])} | {fmt(m['recallk'])} | {fmt(m['page_hitk'])} | {fmt(m['context_words'], 0)} |")
    lines += ["", "## Knowledge-gap signal", "",
              "| Site | Config | Conf. answerable | Conf. unanswerable | AUROC | False gap @τ | Missed gap @τ | Best τ |",
              "|---|---|---|---|---|---|---|---|"]
    for r in summary["results"]:
        m = r["retrieval"]
        lines.append(f"| {r['site']} | {r['config']} | {fmt(m['mean_conf_answerable'])} | {fmt(m['mean_conf_unanswerable'])} "
                     f"| {fmt(m['auroc'])} | {fmt(m['false_gap'])} | {fmt(m['missed_gap'])} | {fmt(m['best_tau'])} |")
    lines += ["", "## Chunk quality", "",
              "| Site | Config | Chunks | Mean words | Median | P10–P90 | Tiny (<50w) | Cross-section | Code split |",
              "|---|---|---|---|---|---|---|---|---|"]
    for r in summary["results"]:
        c = r["chunk_stats"]
        w = c["words"]
        lines.append(f"| {r['site']} | {r['config']} | {c['chunks']} | {w['mean']:.0f} | {w['median']:.0f} "
                     f"| {w['p10']:.0f}–{w['p90']:.0f} | {fmt(c['tiny_rate'])} | {fmt(c['cross_section_rate'])} "
                     f"| {fmt(c['code_split_rate'])} |")
    if summary["comparisons"]:
        lines += ["", f"## Paired bootstrap against `{BASELINE}` (95% CI, 2000 resamples)", "",
                  "| Site | Config | Metric | Δ mean | CI | Significant |", "|---|---|---|---|---|---|"]
        for c in summary["comparisons"]:
            lines.append(f"| {c['site']} | {c['config']} vs {c['baseline']} | {c['metric']} | {fmt(c['mean_diff'])} "
                         f"| [{fmt(c['ci_low'])}, {fmt(c['ci_high'])}] | {'yes' if c['significant'] else 'no'} |")
    if summary["transfer"]:
        lines += ["", "## Threshold transfer", "",
                  "τ chosen on one site (best balanced accuracy), applied unchanged to another.", "",
                  "| Config | Tuned on | Applied to | τ | Balanced acc. (transferred) | Balanced acc. (own best) |",
                  "|---|---|---|---|---|---|"]
        for t in summary["transfer"]:
            lines.append(f"| {t['config']} | {t['from']} | {t['to']} | {fmt(t['tau'])} | {fmt(t['balanced_transferred'])} "
                         f"| {fmt(t['balanced_own'])} |")
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_csvs(out: Path, summary: dict, per_question: list[dict]) -> None:
    with open(out / "retrieval.csv", "w", newline="") as f:
        fields = ["site", "config", "chunker", "size"] + list(summary["results"][0]["retrieval"].keys())
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in summary["results"]:
            w.writerow({"site": r["site"], "config": r["config"], "chunker": r["chunker"], "size": r["size"], **r["retrieval"]})
    with open(out / "chunk_stats.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["site", "config", "chunks", "mean_words", "median_words", "p10", "p90", "tiny_rate",
                    "cross_section_rate", "code_blocks", "code_split_rate"])
        for r in summary["results"]:
            c = r["chunk_stats"]
            w.writerow([r["site"], r["config"], c["chunks"], c["words"]["mean"], c["words"]["median"],
                        c["words"]["p10"], c["words"]["p90"], c["tiny_rate"], c["cross_section_rate"],
                        c["code_blocks"], c["code_split_rate"]])
    with open(out / "per_question.csv", "w", newline="") as f:
        keys = sorted({k for row in per_question for k in row})
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(per_question)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(sites: list[str], chunker_names: list[str], sizes: list[int], overlap: int, k: int,
        tau: float, unanswerable_per_site: int) -> Path:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out = RESULTS / run_id
    out.mkdir(parents=True, exist_ok=True)

    pages = {s: load_pages(s) for s in sites}
    questions = {s: load_questions(s) for s in sites}
    if len(sites) < 2:
        log.warning("Only one site: there are no unanswerable questions, so gap metrics are skipped.")

    rng = random.Random(11)
    unanswerable: dict[str, list[dict]] = {}
    for s in sites:
        others = [q for o in sites if o != s for q in questions[o]]
        rng.shuffle(others)
        unanswerable[s] = others[:unanswerable_per_site]

    results, per_question = [], []
    rows_by: dict[tuple[str, str], list[dict]] = {}
    for s in sites:
        for size in sizes:
            for name in chunker_names:
                config = f"{name}@{size}"
                log.info("%s / %s", s, config)
                chunks = chunk_site(pages[s], name, size, overlap)
                stats = chunk_stats(pages[s], chunks)
                rows = score_config(chunks, questions[s], unanswerable[s], k)
                rows_by[(s, config)] = rows
                for r in rows:
                    per_question.append({"site": s, "config": config, **r})
                results.append({
                    "site": s, "config": config, "chunker": name, "size": size,
                    "chunk_stats": stats, "retrieval": summarise(rows, tau),
                })

    # Paired bootstrap against the heading chunker at the same size.
    comparisons = []
    for s in sites:
        for size in sizes:
            base_rows = rows_by.get((s, f"{BASELINE}@{size}"))
            if not base_rows:
                continue
            base = {r["qid"]: r for r in base_rows if r["answerable"]}
            for name in chunker_names:
                if name == BASELINE:
                    continue
                other = {r["qid"]: r for r in rows_by[(s, f"{name}@{size}")] if r["answerable"]}
                shared = sorted(set(base) & set(other))
                for metric in ("rr", "recallk"):
                    ci = M.paired_bootstrap([other[q][metric] for q in shared], [base[q][metric] for q in shared])
                    comparisons.append({"site": s, "config": f"{name}@{size}", "baseline": f"{BASELINE}@{size}",
                                        "metric": "MRR" if metric == "rr" else f"Recall@{k}", **ci})

    # Threshold transfer between sites, per config.
    transfer = []
    configs = sorted({r["config"] for r in results})
    for config in configs:
        for a in sites:
            for b in sites:
                if a == b or (a, config) not in rows_by or (b, config) not in rows_by:
                    continue
                ra, rb = rows_by[(a, config)], rows_by[(b, config)]
                pos_a = [r["confidence"] for r in ra if r["answerable"]]
                neg_a = [r["confidence"] for r in ra if not r["answerable"]]
                pos_b = [r["confidence"] for r in rb if r["answerable"]]
                neg_b = [r["confidence"] for r in rb if not r["answerable"]]
                tau_a, tau_b = M.best_threshold(pos_a, neg_a), M.best_threshold(pos_b, neg_b)
                if tau_a is None or tau_b is None:
                    continue
                transfer.append({
                    "config": config, "from": a, "to": b, "tau": tau_a,
                    "balanced_transferred": M.gap_rates(pos_b, neg_b, tau_a)["balanced_accuracy"],
                    "balanced_own": M.gap_rates(pos_b, neg_b, tau_b)["balanced_accuracy"],
                })

    site_meta = []
    for s in sites:
        meta_path = site_dir(s) / "meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
        site_meta.append({
            "site": s, "name": meta.get("name", s), "generator": meta.get("generator", "unknown"),
            "pages": len(pages[s]), "words": meta.get("total_words", 0),
            "crawled_at": meta.get("crawled_at", ""), "questions": len(questions[s]),
            "review": question_review_stats(s),
        })

    summary = {
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "embedding_model": settings.embedding_model,
        "k": k, "tau": tau, "overlap": overlap, "sizes": sizes, "chunkers": chunker_names,
        "relevance_threshold": M.RELEVANCE_THRESHOLD,
        "containment_threshold": M.CONTAINMENT_THRESHOLD,
        "sites": site_meta, "results": results, "comparisons": comparisons, "transfer": transfer,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_csvs(out, summary, per_question)
    write_report(out, summary)
    shutil.copy(out / "summary.json", RESULTS / "latest.json")
    log.info("Done. Tables in %s", out / "report.md")
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sites", required=True, help="Comma-separated, e.g. plausible,fastapi")
    parser.add_argument("--chunkers", default=",".join(CHUNKERS))
    parser.add_argument("--sizes", default=str(settings.chunk_target_words), help="Words, e.g. 120,220,400")
    parser.add_argument("--overlap", type=int, default=settings.chunk_overlap_words)
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--tau", type=float, default=settings.low_confidence_threshold)
    parser.add_argument("--unanswerable", type=int, default=50, help="Cross-site questions per site")
    args = parser.parse_args()

    names = [c.strip() for c in args.chunkers.split(",") if c.strip()]
    unknown = [c for c in names if c not in CHUNKERS]
    if unknown:
        raise SystemExit(f"Unknown chunker(s): {', '.join(unknown)}. Choose from {', '.join(CHUNKERS)}.")
    run([s.strip() for s in args.sites.split(",")], names,
        [int(x) for x in args.sizes.split(",")], args.overlap, args.k, args.tau, args.unanswerable)


if __name__ == "__main__":
    main()
