#!/usr/bin/env python3
"""
Phase 3 - Step 0: diagnostics.

Answers the questions the module designs branch on, BEFORE any module is written.

Q1  Record-or-value?   For P31/P22/P33/P32 (sex, occupation, person-status, race) - does the
                       property point at a RECORD ITEM (simple rename) or at a CV VALUE
                       (record node must be MINTED)?  P42 (hasAge) is the control: we know
                       it points at real Age Record items.
Q2  Reified?           Do ep:Pxx -> statement nodes exist, and do they carry qualifiers? If
                       so, re-type the statement node instead of minting (cheaper, truer).
Q3  Baseline counts    Instances per KEEP wiki class - the numbers each module's output is
                       checked against.
Q4  Relationships      What do the 8 collapsed relationship properties actually point at?
                       (PHASE3-PLAN issue 8.)

Writes CSVs to phase3/diagnostics/ and prints an interpretation.

Usage (from repo root):
    python phase3\\step0_diagnostics.py --dataset Enslaved-dataset
Standard library only.
"""

import argparse
import csv
import os
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import MAPPINGS, OUT_DIAGNOSTICS, ensure  # noqa: E402

PREFIXES = """
PREFIX ed:       <https://lod.enslaved.org/entity/>
PREFIX edt:      <https://lod.enslaved.org/prop/direct/>
PREFIX ep:       <https://lod.enslaved.org/prop/>
PREFIX rdfs:     <http://www.w3.org/2000/01/rdf-schema#>
PREFIX wikibase: <http://wikiba.se/ontology#>
"""

# --- Q1: does the record-link property point at a record item or a bare value? ----------
Q1 = PREFIXES + """
SELECT ?p ?targetType ?targetTypeLabel (COUNT(*) AS ?n)
WHERE {
    VALUES ?p { edt:P31 edt:P22 edt:P33 edt:P32 edt:P42 }
    ?s ?p ?target .
    OPTIONAL {
        ?target edt:P1 ?targetType .
        OPTIONAL { ?targetType rdfs:label ?targetTypeLabel . FILTER(lang(?targetTypeLabel)="en") }
    }
}
GROUP BY ?p ?targetType ?targetTypeLabel
ORDER BY ?p DESC(?n)
"""

# --- Q2: is the fact reified, and do statements carry qualifiers? -----------------------
Q2 = PREFIXES + """
SELECT ?p (COUNT(DISTINCT ?stmt) AS ?statements) (COUNT(?qual) AS ?qualifierUses)
WHERE {
    VALUES ?p { ep:P31 ep:P22 ep:P33 ep:P42 ep:P30 ep:P27 ep:P28 }
    ?s ?p ?stmt .
    OPTIONAL {
        ?stmt ?qual ?qv .
        FILTER( STRSTARTS( STR(?qual), "https://lod.enslaved.org/prop/qualifier/" ) )
    }
}
GROUP BY ?p
ORDER BY DESC(?statements)
"""

# --- Q4: what do the collapsed relationship properties point at? ------------------------
Q4 = PREFIXES + """
SELECT ?p ?targetType ?targetTypeLabel (COUNT(*) AS ?n)
WHERE {
    VALUES ?p { edt:P37 edt:P38 edt:P39 edt:P40 edt:P41 edt:P43 edt:P44 edt:P48 edt:P67 edt:P68 }
    ?s ?p ?target .
    OPTIONAL {
        ?target edt:P1 ?targetType .
        OPTIONAL { ?targetType rdfs:label ?targetTypeLabel . FILTER(lang(?targetTypeLabel)="en") }
    }
}
GROUP BY ?p ?targetType ?targetTypeLabel
ORDER BY ?p DESC(?n)
"""


def q3_baseline(keep_classes) -> str:
    """Q3 built from the KEEP wiki classes in the reconciled mapping."""
    values = " ".join(f"ed:{q}" for q in keep_classes)
    return PREFIXES + f"""
SELECT ?cls ?label (COUNT(?x) AS ?instances)
WHERE {{
    VALUES ?cls {{ {values} }}
    ?x edt:P1 ?cls .
    OPTIONAL {{ ?cls rdfs:label ?label . FILTER(lang(?label)="en") }}
}}
GROUP BY ?cls ?label
ORDER BY DESC(?instances)
"""


def run(endpoint: str, query: str) -> str:
    data = urllib.parse.urlencode({"query": query}).encode("utf-8")
    req = urllib.request.Request(
        endpoint, data=data,
        headers={"Accept": "text/csv", "Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req) as resp:
        return resp.read().decode("utf-8")


def short(v: str) -> str:
    return v.rsplit("/", 1)[-1] if v.startswith("http") else v


def main() -> int:
    ap = argparse.ArgumentParser(description="Phase 3 Step 0 diagnostics.")
    ap.add_argument("--server", default="http://localhost:3030")
    ap.add_argument("--dataset", default="Enslaved-dataset")
    args = ap.parse_args()

    endpoint = f"{args.server.rstrip('/')}/{args.dataset}/query"
    outdir = ensure(OUT_DIAGNOSTICS)

    # KEEP wiki classes for Q3
    keep = []
    with open(os.path.join(MAPPINGS, "mapping-classes-reconciled.csv"), encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["bucket"].strip().upper() == "KEEP":
                keep.append(row["wiki_class"].strip())

    jobs = [
        ("q1_record_or_value.csv", Q1,
         "Q1  record-link targets: is the target a RECORD ITEM or a bare CV VALUE?"),
        ("q2_reification.csv", Q2,
         "Q2  reification: statement nodes and qualifier usage per property"),
        ("q3_baseline_counts.csv", q3_baseline(keep),
         f"Q3  baseline instance counts for {len(keep)} KEEP classes"),
        ("q4_relationships.csv", Q4,
         "Q4  what the 8 collapsed relationship properties point at"),
    ]

    print(f"Querying {endpoint}\n")
    for filename, query, title in jobs:
        print("=" * 78)
        print(title)
        try:
            out = run(endpoint, query)
        except Exception as exc:  # noqa: BLE001
            print(f"  ERROR: {exc}")
            continue
        path = os.path.join(outdir, filename)
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(out)
        rows = list(csv.DictReader(out.splitlines()))
        for r in rows[:25]:
            print("   " + "  ".join(f"{short(v)}" for v in r.values()))
        if len(rows) > 25:
            print(f"   ... {len(rows) - 25} more rows")
        print(f"   -> {path}  ({len(rows)} rows)\n")

    print("=" * 78)
    print("HOW TO READ THIS")
    print("""
Q1  For each of P31/P22/P33/P32, look at ?targetType:
      * target has instance-of a RECORD class (like 'Sex Record')  -> simple RENAME
      * target has instance-of a CV class ('Sex', 'Occupation')    -> MINT the record node
      * target has NO type (a literal, e.g. P32)                   -> MINT from the string
    Compare against P42 (control) which should show real Age Record items.

Q2  statements > 0 AND qualifierUses > 0  -> re-type the statement node as the record
    (preserves qualifiers, no minting needed).
    statements > 0 but qualifierUses = 0  -> reification is empty scaffolding; mint instead.

Q3  Record these numbers. Each module's output count must match its source class count.

Q4  If all 8 point at PERSONS (not at relationship-type values), the relationship TYPE
    lives only in the choice of property - confirming issue 8 is lossy, and the type must
    be derived from which Pxx matched.
""")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
