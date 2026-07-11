"""Offline, name-free acceptance/QA harnesses -- read-only tooling that drives existing pure contracts
and seams over a caller-supplied corpus directory. Nothing under this package writes to a product store,
makes a network call, or names a customer/vendor. See ``run_handwritten_corpus_acceptance.py``."""
from __future__ import annotations
