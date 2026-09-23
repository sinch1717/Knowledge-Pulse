"""Offline experiments for the paper: how chunking strategy affects retrieval
and the knowledge-gap signal across documentation sites built on different
generators.

Kept apart from the app on purpose. Nothing here writes to the app database or
the Chroma index; every run reads a frozen snapshot and writes plain files under
data/research/, so results are reproducible and the demo data is untouched.

    python -m research.snapshot  --site plausible
    python -m research.questions --site plausible --count 100
    python -m research.run       --sites plausible,fastapi
"""
