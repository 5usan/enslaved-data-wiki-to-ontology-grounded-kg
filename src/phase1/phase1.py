#!/usr/bin/env python3
"""
Phase 1 - Extract the mapping table from the Enslaved Wikibase dump.

Queries a running Jena Fuseki endpoint (chunks already loaded) and writes two CSVs:
  - mapping-properties.csv : every Pxx property (label, Wikibase type, object/datatype kind)
  - mapping-classes.csv    : every Qxx that acts as a class (instance-of / subclass-of) + label

These are pure EXTRACTION (what the dump declares). Matching to the ontology and dropping
Wikibase plumbing happens in Phase 2.

Usage (from the repo root):
    python phase1\\phase1.py --dataset Enslaved-dataset

--dataset must match the dataset name in the Fuseki UI (http://localhost:3030).
No third-party packages required (standard library only).
"""

import argparse
import os
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import MAPPINGS, ensure  # noqa: E402

# ---------------------------------------------------------------------------
# Phase 1 queries
# ---------------------------------------------------------------------------

Q_PROPERTIES = r"""
# PROPERTY side of the mapping table.
# WikibaseItem => points at another entity => object property;
# every other propertyType is a literal => datatype property.
PREFIX wikibase: <http://wikiba.se/ontology#>
PREFIX rdfs:     <http://www.w3.org/2000/01/rdf-schema#>
PREFIX xsd:      <http://www.w3.org/2001/XMLSchema#>

SELECT ?prop ?label ?propType ?kind
WHERE {
    ?prop a wikibase:Property ;
          rdfs:label ?label ;
          wikibase:propertyType ?propType .
    BIND( IF(?propType = wikibase:WikibaseItem, "object", "datatype") AS ?kind )
}
ORDER BY xsd:integer( STRAFTER( STR(?prop), "entity/P" ) )
"""

Q_CLASSES = r"""
# CLASS side of the mapping table.
# A Q-item is a class when items declare themselves its "instance of" (P1),
# or when it appears on either side of "subclass of" (P2).
PREFIX edt:  <https://lod.enslaved.org/prop/direct/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX xsd:  <http://www.w3.org/2001/XMLSchema#>

SELECT DISTINCT ?class ?label
WHERE {
    {  ?x edt:P1 ?class      }    # object of "instance of"
    UNION
    {  ?x edt:P2 ?class      }    # super-class side of "subclass of"
    UNION
    {  ?class edt:P2 ?super  }    # sub-class side of "subclass of"
    ?class rdfs:label ?label .
}
ORDER BY xsd:integer( STRAFTER( STR(?class), "entity/Q" ) )
"""

JOBS = [
    ("mapping-properties.csv", Q_PROPERTIES),
    ("mapping-classes.csv",    Q_CLASSES),
]

# ---------------------------------------------------------------------------


def run_query(endpoint: str, query: str) -> str:
    """POST a SPARQL query to Fuseki and return CSV results."""
    data = urllib.parse.urlencode({"query": query}).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=data,
        headers={
            "Accept": "text/csv",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with urllib.request.urlopen(req) as resp:
        return resp.read().decode("utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Phase 1 mapping extractor (Fuseki).")
    ap.add_argument("--server", default="http://localhost:3030", help="Fuseki base URL")
    ap.add_argument("--dataset", default="Enslaved-dataset", help="Fuseki dataset name")
    args = ap.parse_args()

    endpoint = f"{args.server.rstrip('/')}/{args.dataset}/query"
    out_dir = ensure(MAPPINGS)

    print(f"Querying {endpoint}")
    for filename, query in JOBS:
        try:
            csv_text = run_query(endpoint, query)
        except Exception as exc:  # noqa: BLE001
            print(f"  ERROR running query for {filename}: {exc}", file=sys.stderr)
            return 1
        out_path = os.path.join(out_dir, filename)
        with open(out_path, "w", encoding="utf-8", newline="") as fh:
            fh.write(csv_text)
        rows = max(csv_text.count("\n") - 1, 0)
        print(f"  wrote {filename}  (~{rows} rows)")

    print("Done. Next: Phase 2 - match labels to enslaved-v2.ttl, drop the plumbing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
