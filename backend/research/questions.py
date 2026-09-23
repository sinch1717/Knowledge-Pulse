"""Build a frozen question set for one site.

Gold passages of 40-120 words are sampled from the prose of the snapshot (code
blocks are left out), at most two per page so one long page cannot dominate.
An LLM writes one question per passage, five passages per call to spare the
quota. Each question keeps its gold page and passage text.

    python -m research.questions --site plausible --count 100

Then review a sample: open data/research/<site>/questions.json and set
"accepted": false on any question that is unclear or not answerable from its
passage. The runner skips rejected questions, and the acceptance rate goes in
the paper. Use a non-reasoning model (llama-3.3-70b-versatile or Gemini);
reasoning models can spend their whole budget thinking and return nothing.
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import time

from app import llm
from research.common import load_pages, site_dir

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("questions")

MIN_WORDS, MAX_WORDS = 40, 120
PER_CALL = 5

PROMPT = """Below are {n} numbered passages from the documentation of {site}.

For each passage write ONE question a real user of the product might type, that
the passage fully answers on its own.

Rules:
- Phrase it the way a user would, not as an exam question. Do not say "the passage".
- Do not copy long phrases from the passage; paraphrase.
- The question must make sense without seeing the passage.

{passages}

Return a JSON object: {{"questions": [{{"id": 1, "question": "..."}}, ...]}} with one entry per passage."""


def gold_passages(site: str) -> list[dict]:
    out: list[dict] = []
    for page in load_pages(site):
        heading = page.title
        current: list[str] = []

        def flush() -> None:
            text = " ".join(current).split()
            if len(text) >= MIN_WORDS:
                out.append({"url": page.url, "heading": heading, "gold_text": " ".join(text[:MAX_WORDS])})
            current.clear()

        for block in page.blocks():
            if block.kind == "heading":
                flush()
                heading = block.text
            elif block.kind == "code":
                flush()
            else:
                current.append(block.text)
                if len(" ".join(current).split()) >= MAX_WORDS:
                    flush()
        flush()
    return out


def sample(passages: list[dict], count: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    rng.shuffle(passages)
    per_page: dict[str, int] = {}
    chosen = []
    for p in passages:
        if per_page.get(p["url"], 0) >= 2:
            continue
        per_page[p["url"]] = per_page.get(p["url"], 0) + 1
        chosen.append(p)
        if len(chosen) >= count:
            break
    return chosen


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", required=True)
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--sleep", type=float, default=4.0, help="Seconds between LLM calls (rate limits)")
    args = parser.parse_args()

    out_path = site_dir(args.site) / "questions.json"
    if out_path.exists():
        raise SystemExit(f"{out_path} exists. Questions are frozen once made; delete it to regenerate.")

    passages = sample(gold_passages(args.site), args.count, args.seed)
    log.info("Sampled %d gold passages from %s", len(passages), args.site)

    questions: list[dict] = []
    for start in range(0, len(passages), PER_CALL):
        batch = passages[start : start + PER_CALL]
        listing = "\n\n".join(f"[{i + 1}] {p['gold_text']}" for i, p in enumerate(batch))
        try:
            result = llm.complete_json(
                PROMPT.format(n=len(batch), site=args.site, passages=listing),
                system="You write realistic questions from product users.",
                temperature=0.4,
                max_tokens=900,
            )
            items = result.get("questions", []) if isinstance(result, dict) else result
        except llm.LLMError as exc:
            log.warning("Batch at %d failed: %s", start, exc)
            items = []
        for item in items if isinstance(items, list) else []:
            try:
                idx = int(item["id"]) - 1
                text = str(item["question"]).strip()
            except (KeyError, TypeError, ValueError):
                continue
            if 0 <= idx < len(batch) and text:
                p = batch[idx]
                questions.append(
                    {
                        "id": f"{args.site}_q{len(questions) + 1:03d}",
                        "site": args.site,
                        "question": text,
                        "url": p["url"],
                        "heading": p["heading"],
                        "gold_text": p["gold_text"],
                        "accepted": None,
                    }
                )
        log.info("%d/%d questions", len(questions), len(passages))
        time.sleep(args.sleep)

    out_path.write_text(json.dumps(questions, indent=2))
    log.info("Wrote %d questions to %s. Review a sample before running.", len(questions), out_path)


if __name__ == "__main__":
    main()
