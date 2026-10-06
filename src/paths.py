"""Canonical project paths — single source of truth for the repo layout.

Every script under src/ imports from here rather than recomputing
`dirname(dirname(...))` chains, so moving a directory means editing one file.

Usage from any script in src/<phase>/:

    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from paths import MAPPINGS, ONTOLOGY, OUT_PHASE3
"""

import os

# src/paths.py -> src -> repo root
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Inputs (version-controlled, small)
ONTOLOGY = os.path.join(ROOT, "ontology")       # enslaved-v2.ttl + extracted term lists
MAPPINGS = os.path.join(ROOT, "mappings")       # phase 1/2 wiki->ontology mapping CSVs
DOCS = os.path.join(ROOT, "docs")

# Inputs (large, gitignored)
DATA = os.path.join(ROOT, "data")
DATA_RAW = os.path.join(DATA, "raw")            # enslaved_dump.rdf
CHUNKS = os.path.join(DATA_RAW, "chunks")       # chunk_0.ttl .. chunk_22.ttl

# Generated artefacts (gitignored)
OUT = os.path.join(ROOT, "out")
OUT_PHASE3 = os.path.join(OUT, "phase3")        # one CONSTRUCT result .ttl per module
OUT_DIAGNOSTICS = os.path.join(OUT, "diagnostics")

# Query sources
QUERIES_PHASE3 = os.path.join(ROOT, "src", "phase3", "queries")


def ensure(directory: str) -> str:
    """Create `directory` if missing and return it. For output paths."""
    os.makedirs(directory, exist_ok=True)
    return directory
