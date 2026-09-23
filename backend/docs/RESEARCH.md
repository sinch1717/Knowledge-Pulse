# Chunking research: runbook and method

The experiment asks one question: **does the way documentation is chunked change
what a RAG assistant retrieves, and how reliably its retrieval confidence flags
gaps in the docs?** It compares four chunkers across documentation sites built on
different generators.

Everything runs offline against frozen snapshots and writes plain files under
`data/research/`. It never touches the app database or the Chroma index, so the
demo data stays as it is.

## Commands, in order

Run from the backend folder with the virtual environment active.

```bash
# 1. Freeze each site (about 2-4 minutes per site at 250 pages)
python -m research.snapshot --site plausible
python -m research.snapshot --site fastapi

# 2. Generate questions (about 20 LLM calls per site; uses LLM_PROVIDER from .env)
python -m research.questions --site plausible --count 100
python -m research.questions --site fastapi --count 100

# 3. Review a sample (see below), then run. Local embeddings only, no LLM calls.
python -m research.run --sites plausible,fastapi
```

Optional size sweep, which is the paper's second research question:

```bash
python -m research.run --sites plausible,fastapi --sizes 120,220,400
```

Results land in `data/research/results/<timestamp>/`, and the latest run also
goes to `data/research/results/latest.json`, which the website's Research page
reads. `report.md` in the run folder holds paper-ready tables.

### Before step 2

- Check `data/research/<site>/meta.json`. `page_count` should be well above 20
  and `generator` should name the site generator. If pages are few, fix
  `content_selector` or `include_prefix` in `research/sites.json` and snapshot
  again.
- Open two or three pages in `pages.json` and check the HTML is article content
  only, with no navigation or footer text.
- Set `GROQ_MODEL=llama-3.3-70b-versatile` or use Gemini. A reasoning model will
  return empty JSON.

### Reviewing questions (about 20 minutes per site)

Open `data/research/<site>/questions.json`. For the first 30 questions, set
`"accepted": true` or `false`:

- `true` if the question is clear on its own and its `gold_text` fully answers it.
- `false` if it is vague, quotes the passage, or needs information not in the passage.

Rejected questions are dropped from the run. Unreviewed ones (`null`) are kept.
The acceptance rate over the reviewed 30 is reported in the Sites table and
belongs in the paper as a measure of question-set quality.

Questions are frozen once made. `research.questions` refuses to overwrite an
existing file; delete it deliberately to regenerate.

## Adding a site later

Add an entry to `research/sites.json` (Flask and Docusaurus are already there),
then snapshot, generate questions, and include it in `--sites`. More sites give
the threshold-transfer result more weight.

## Method, for the paper

**Sites and snapshots.** Each site is crawled breadth-first from its entry URL,
restricted to a path prefix, excluding translations and versioned copies,
honouring `robots.txt`, with a 0.5 s delay and a 250-page cap. The main content
region is selected per site and navigation, footers and anchor links are
removed. Pages with fewer than 30 words are dropped. The crawl date and
generator are recorded.

**Chunkers.** All four read the same ordered blocks (headings, paragraphs, list
items, table cells, code) of the same snapshot.

| Chunker | Boundaries | Embedded text |
|---|---|---|
| Fixed window | Every `size` words, `overlap` words shared | Chunk text |
| Recursive | Whole paragraphs packed up to `size`; long paragraphs split on sentences, then words; no overlap | Chunk text |
| Heading-aware | Cut at headings; sections longer than `size` windowed with `overlap` | Chunk text |
| Heading + path | Same as heading-aware | Heading path, then chunk text |

Comparing the last two isolates the effect of heading *context* from the effect
of heading *boundaries*.

**Questions.** Gold passages of 40-120 words are sampled from prose (not code),
at most two per page, with a fixed seed. An LLM writes one question per passage.
A sample of 30 per site is reviewed by hand.

**Retrieval.** Chunks and questions are embedded with all-MiniLM-L6-v2 (the
app's model), and retrieval is exact cosine search.

**Relevance.** No chunk ids are shared between chunkers, so relevance is judged
on text. A retrieved chunk is relevant if it contains at least 50% of the gold
passage's word 3-grams, or if at least 70% of the chunk's 3-grams lie inside the
gold passage (with at least 10 shared). The second clause keeps small chunk
sizes from being penalised for being smaller than the passage.

**Retrieval metrics** (answerable questions):

- Hit@1 and Hit@k: a relevant chunk ranked first, or within the top k (k = 5).
- MRR: reciprocal rank of the first relevant chunk within the top 10.
- Recall@k: share of the gold passage's 3-grams covered by the union of the top
  k chunks. Rewards retrieving an answer that a chunker split in two.
- Page hit@k: any top-k chunk comes from the gold page.
- Context words: total words in the top k, the cost side of the trade-off.

**Knowledge-gap metrics.** Unanswerable questions for a site are questions from
the other sites in the run (50 per site). Confidence is the app's own retrieval
confidence: 0.6 × top similarity + 0.4 × mean of the top five.

- AUROC: probability that an answerable question has higher confidence than an
  unanswerable one.
- False gap rate at τ = 0.40: answerable questions flagged as gaps.
- Missed gap rate at τ: unanswerable questions not flagged.
- Best τ: threshold with the highest balanced accuracy on that site.
- Threshold transfer: τ tuned on one site, balanced accuracy on the other.

**Chunk quality** (no questions needed):

- Chunk count and word-length distribution (mean, median, P10, P90).
- Tiny-chunk rate: chunks under 50 words.
- Cross-section rate: chunks whose text comes substantially from two or more
  heading sections (at least 3 3-grams and 10% of the chunk from each).
- Code-split rate: code blocks of 20+ words with no single chunk holding 90% of
  them.

**Statistics.** Each chunker is compared with heading-aware at the same size by
a paired bootstrap over the same questions (2000 resamples, fixed seed). A
difference is reported as significant when the 95% percentile interval excludes
zero.

## Threats to validity (write these up honestly)

- **Generated questions.** Questions written from a passage share its wording,
  which favours lexical overlap. The manual review and the acceptance rate
  address clarity, not this bias.
- **Easy unanswerables.** Cross-site questions (analytics questions put to a web
  framework's docs) are far from the corpus, so AUROC will be high for every
  chunker. The false-gap rate is the more discriminating number. In-domain
  unanswerable questions would be a stronger test and are future work.
- **One embedding model.** Results may differ with larger embedding models.
- **Chunk size is matched in the setting, not in the outcome.** Heading-aware
  chunks are shorter on average because sections are short. Report mean chunk
  length next to every retrieval number, and use the size sweep to show the
  trend holds across sizes.
- **Two sites** is a small sample for the transfer result; say so, and add
  Flask and Docusaurus when time allows.
