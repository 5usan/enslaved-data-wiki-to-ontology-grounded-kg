#!/usr/bin/env python3
"""
Phase 2 - Coverage report: which ontology terms have a wiki source, and which don't.

Set-difference of the ontology's own classes/properties against what the wiki mapping
actually covers, so every un-populated ontology term gets an explicit disposition instead
of being silently missing.

Reads (from the repo root):
  - ontology-classes.txt              (produced earlier)
  - ontology-properties.csv           (produced earlier)
  - mapping-classes-reconciled.csv    (Phase 2; preferred)   -- else falls back to:
  - mapping-classes.csv               (Phase 1 raw)
  - mapping-properties-reconciled.csv (Phase 2; preferred)   -- else:
  - mapping-properties.csv            (Phase 1 raw)

Writes:
  - coverage-gaps.csv   one row per ontology term:
        ontology_term, term_type, has_wiki_source, disposition, note

Dispositions (prefilled where inferable; REVIEW the blanks/guesses):
  map            -> a wiki source maps to it directly (KEEP)
  synthesize     -> ontology wants an intermediate/record node the wiki stores flat;
                    a CONSTRUCT must MINT the node   (verify against the data)
  via-reification-> may come from a wikibase:Statement node re-typed as this record
                    (verify the statements carry the needed qualifiers)
  leave-empty    -> no wiki data; valid to leave un-populated (confirm min-cardinality 0)

No third-party packages. Usage (from repo root):  python phase2\\coverage_report.py
"""

import argparse
import csv
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import MAPPINGS, ONTOLOGY, ensure  # noqa: E402

# Ontology classes that model INTERMEDIATE / n-ary / record structure. When one of these
# has no direct wiki source it usually needs a minted node or a re-typed statement, not
# "leave-empty". Edit this set as you learn the data.
STRUCTURAL_CLASSES = {
    "NameRecord", "NameVariant", "SexRecord", "PersonRecord", "RaceRecord",
    "OccupationRecord", "OriginRecord", "PersonStatusRecord", "ParticipantRoleRecord",
    "InterAgentRelationshipRecord", "Description", "TimeSpan", "TemporalExtent",
    "SpatialExtent", "Coordinates", "ProvenanceActivity", "ExternalReference",
    "ExternalReferent",
}


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def load_lines(path):
    with open(path, encoding="utf-8") as f:
        return [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]


def covered_from_reconciled(path, target_col):
    """Return set of ':OntologyTerm' local names that appear as KEEP targets."""
    covered = set()
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("bucket") == "KEEP" and row.get(target_col):
                covered.add(row[target_col].lstrip(":"))
    return covered


def covered_from_raw(path, label_col, onto_names):
    """Fallback: fuzzy-match raw mapping labels to ontology local names."""
    onto_norm = {norm(n): n for n in onto_names}
    covered = set()
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            n = norm(row[label_col])
            if n in onto_norm:
                covered.add(onto_norm[n]); continue
            for suf in ("", "record", "types", "cv", "typecv"):
                if n + suf in onto_norm:
                    covered.add(onto_norm[n + suf]); break
    return covered


def pick(root, preferred, fallback):
    p = os.path.join(root, preferred)
    return (p, True) if os.path.exists(p) else (os.path.join(root, fallback), False)


def class_disposition(name, has_source):
    if has_source:
        return "map", "direct wiki source"
    if name in STRUCTURAL_CLASSES or name.endswith("Record"):
        return "synthesize", "intermediate/record node - mint or re-type a statement (verify)"
    return "leave-empty", "no wiki source found - confirm min-cardinality 0"


def prop_disposition(name, kind, has_source):
    if has_source:
        return "map", "direct wiki source"
    # object properties that link to structural nodes are usually needed if their
    # target class is synthesized.
    if kind == "object":
        return "synthesize", "may be needed to attach a synthesized node (verify)"
    return "leave-empty", "no wiki source found"


def main() -> int:
    ap = argparse.ArgumentParser(description="Phase 2 coverage report.")
    ap.add_argument("--ontology-dir", default=ONTOLOGY)
    ap.add_argument("--mappings-dir", default=MAPPINGS)
    args = ap.parse_args()
    onto_dir, maps = args.ontology_dir, ensure(args.mappings_dir)

    onto_classes = [ln.lstrip(":") for ln in load_lines(os.path.join(onto_dir, "ontology-classes.txt"))]
    onto_props = {}
    with open(os.path.join(onto_dir, "ontology-properties.csv"), encoding="utf-8") as f:
        for row in csv.DictReader(f):
            onto_props[row["property"].lstrip(":")] = row["kind"]

    # classes coverage
    cpath, recon = pick(maps, "mapping-classes-reconciled.csv", "mapping-classes.csv")
    cls_covered = (covered_from_reconciled(cpath, "ontology_class") if recon
                   else covered_from_raw(cpath, "label", onto_classes))
    # properties coverage
    ppath, recon_p = pick(maps, "mapping-properties-reconciled.csv", "mapping-properties.csv")
    prop_covered = (covered_from_reconciled(ppath, "ontology_property") if recon_p
                    else covered_from_raw(ppath, "label", onto_props.keys()))

    rows = []
    for c in sorted(onto_classes):
        has = c in cls_covered
        disp, note = class_disposition(c, has)
        rows.append([f":{c}", "class", "yes" if has else "no", disp, note])
    for p in sorted(onto_props):
        has = p in prop_covered
        disp, note = prop_disposition(p, onto_props[p], has)
        rows.append([f":{p}", f"{onto_props[p]}-property", "yes" if has else "no", disp, note])

    out = os.path.join(maps, "coverage-gaps.csv")
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ontology_term", "term_type", "has_wiki_source", "disposition", "note"])
        w.writerows(rows)

    covered = sum(1 for r in rows if r[2] == "yes")
    print(f"class source: {'reconciled' if recon else 'raw fallback'} | "
          f"property source: {'reconciled' if recon_p else 'raw fallback'}")
    print(f"ontology terms: {len(rows)}  covered: {covered}  gaps: {len(rows) - covered}")
    from collections import Counter
    print("dispositions:", dict(Counter(r[3] for r in rows)))
    print(f"wrote {out} - review the 'synthesize' and 'leave-empty' rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
