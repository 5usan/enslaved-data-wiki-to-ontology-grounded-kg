#!/usr/bin/env python3
"""
Phase 2 - Reconcile the Phase 1 mapping against the Enslaved Ontology.

Reads:
  - enslaved-v2.ttl          (the ontology: class + property local names)
  - mapping-classes.csv      (Phase 1 output)
  - mapping-properties.csv    (Phase 1 output)

Writes (to the repo root):
  - mapping-classes-reconciled.csv
  - mapping-properties-reconciled.csv

Each row is sorted into a bucket:
  KEEP        -> a genuine ontology class/property (with proposed target)
  CV_INDIVIDUAL -> a controlled-vocabulary VALUE (becomes a typed instance, not a class)
  DROP        -> Wikibase plumbing / imported upper-ontology term
  REVIEW      -> no confident decision; you decide

Matching is by normalised name (drop spaces/punctuation, lowercase): the wiki LABEL is
compared against the ontology LOCAL NAME, since ontology terms carry no rdfs:label.

NOTHING here is final - the CV/DROP sets below are judgement calls. Review and edit them,
then re-run. No third-party packages required.

Usage (from the repo root):
    python phase2\\phase2.py
"""

import argparse
import csv
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import MAPPINGS, ONTOLOGY, ensure  # noqa: E402

# ===========================================================================
# EDITABLE JUDGEMENT SETS  -  review these; they encode Phase 2 decisions
# ===========================================================================

# Controlled-vocabulary VALUE items -> the ontology Types/CV class they instantiate.
# (normalised label  ->  ontology class)
CV_INDIVIDUALS = {
    # event-type values
    "voyage": ":EventTypes", "birth": ":EventTypes", "death": ":EventTypes",
    "baptismornamingceremony": ":EventTypes", "marriage": ":EventTypes",
    "enslavement": ":EventTypes", "saleortransfer": ":EventTypes",
    "disappearance": ":EventTypes", "legalproceeding": ":EventTypes",
    "employmentapprenticeshiporindenture": ":EventTypes", "narrative": ":EventTypes",
    "healthorsicknessorinjury": ":EventTypes", "residence": ":EventTypes",
    "relocation": ":EventTypes", "familyseparation": ":EventTypes",
    "militaryservice": ":EventTypes", "registration": ":EventTypes",
    "emancipationormanumission": ":EventTypes", "embarkation": ":EventTypes",
    "disembarkation": ":EventTypes", "mortgage": ":EventTypes",
    "appraisal": ":EventTypes", "mention": ":EventTypes", "advertisement": ":EventTypes",
    "membership": ":EventTypes",
    # match-type values
    "closematch": ":MatchType", "nomatch": ":MatchType",
}

# Imported upper-ontology + Wikibase constraint plumbing -> dropped entirely.
DROP_LABELS = {
    "existence", "philosophicalconcept", "class", "ontology", "conceptualmodel", "model",
    "entity", "wikidataidentifier", "relationoftypeconstraint", "propertyconstraint",
    "enslavedhubpropertydefinition", "definition", "enslavedorgitem", "uniqueidentifier",
    "identifier", "namespace", "statement", "representation", "property", "quality",
    "scientificmodelling", "authoritycontrol", "controlledvocabulary",
    "knowledgeorganizationsystem", "variableordermetaclass", "enslavedorgqualifier",
    "intellectualwork", "information", "work", "system", "structure", "communicationmedium",
    "conceptualsystem", "database", "gazetteer", "artificialentity", "product", "culture",
    "humanbehaviour", "behavior", "activity", "catalog", "metaclass", "concept",
    "socialorganismbehavior", "proposition", "sign", "conflictswithconstraint",
    "abstractobject", "mandatoryqualifierconstraint", "viafidentifier", "object",
    "temporalentity", "enslavedorgproperty", "matchclassmodule",
}

# Wikibase / meta PROPERTIES that must NOT become ontology properties.
#   P1 instance of  -> rdf:type   |  P2 subclass of -> rdfs:subClassOf  (handled in Phase 3)
DROP_PROPERTY_LABELS = {
    "instanceof", "subclassof", "equivalentclass", "version", "propertyconstraint",
    "partof", "haspart", "subjectitemofthisproperty", "of", "facetof", "haseffect",
    "hasquality",
}

# ===========================================================================


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def parse_ontology(ttl_path: str):
    """Return (set of class local names, set of property local names)."""
    classes, props = set(), set()
    for line in open(ttl_path, encoding="utf-8"):
        s = line.strip()
        m = re.match(r":([A-Za-z]+) rdf:type owl:Class", s)
        if m:
            classes.add(m.group(1))
        m = re.match(r":([A-Za-z]+) rdf:type owl:(ObjectProperty|DatatypeProperty)", s)
        if m:
            props.add(m.group(1))
    return classes, props


def fuzzy(n: str, onto_norm: dict, suffixes=()):
    """Match normalised name to an ontology term, trying suffix variants then overlap."""
    if n in onto_norm:
        return onto_norm[n], "exact"
    for suf in suffixes:
        if n + suf in onto_norm:
            return onto_norm[n + suf], "fuzzy"
    for k, v in onto_norm.items():
        if n and (n in k or k in n) and abs(len(n) - len(k)) <= 8:
            return v, "fuzzy"
    return "", ""


def reconcile_classes(rows, onto_classes):
    onto_norm = {norm(c): c for c in onto_classes}
    out = []
    for r in rows:
        q = r["class"].split("/")[-1]
        lbl = r["label"]
        n = norm(lbl)
        cls, how = fuzzy(n, onto_norm, suffixes=("record", "types", "cv", "typecv"))
        if cls:
            out.append([q, lbl, "KEEP", ":" + cls, how])
        elif n in CV_INDIVIDUALS:
            out.append([q, lbl, "CV_INDIVIDUAL", CV_INDIVIDUALS[n], "cv value"])
        elif n in DROP_LABELS or lbl.lower().startswith("version "):
            out.append([q, lbl, "DROP", "", "upper-ontology/plumbing"])
        else:
            out.append([q, lbl, "REVIEW", "", "needs decision"])
    return out


def reconcile_properties(rows, onto_props):
    onto_norm = {norm(p): p for p in onto_props}
    out = []
    for r in rows:
        p = r["prop"].split("/")[-1]
        lbl = r["label"]
        kind = r.get("kind", "")
        n = norm(lbl)
        prop, how = fuzzy(n, onto_norm, suffixes=())
        if n in DROP_PROPERTY_LABELS:
            out.append([p, lbl, kind, "DROP", "", "wikibase meta"])
        elif prop:
            out.append([p, lbl, kind, "KEEP", ":" + prop, how])
        else:
            out.append([p, lbl, kind, "REVIEW", "", "needs decision"])
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Phase 2 reconciliation.")
    ap.add_argument("--ontology-dir", default=ONTOLOGY,
                    help="directory holding enslaved-v2.ttl")
    ap.add_argument("--mappings-dir", default=MAPPINGS,
                    help="directory holding the Phase 1 CSVs (also the output dir)")
    args = ap.parse_args()
    onto_dir, maps = args.ontology_dir, ensure(args.mappings_dir)

    onto_classes, onto_props = parse_ontology(os.path.join(onto_dir, "enslaved-v2.ttl"))
    print(f"ontology: {len(onto_classes)} classes, {len(onto_props)} properties")

    cls_rows = list(csv.DictReader(open(os.path.join(maps, "mapping-classes.csv"), encoding="utf-8")))
    prop_rows = list(csv.DictReader(open(os.path.join(maps, "mapping-properties.csv"), encoding="utf-8")))

    cls_out = reconcile_classes(cls_rows, onto_classes)
    prop_out = reconcile_properties(prop_rows, onto_props)

    with open(os.path.join(maps, "mapping-classes-reconciled.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["wiki_class", "wiki_label", "bucket", "ontology_class", "note"])
        w.writerows(cls_out)
    with open(os.path.join(maps, "mapping-properties-reconciled.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["wiki_prop", "wiki_label", "prop_kind", "bucket", "ontology_property", "note"])
        w.writerows(prop_out)

    def tally(rows, idx):
        from collections import Counter
        return dict(Counter(r[idx] for r in rows))

    print("classes  ->", tally(cls_out, 2))
    print("properties ->", tally(prop_out, 3))
    print("Review the REVIEW rows and the editable sets at the top, then re-run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
