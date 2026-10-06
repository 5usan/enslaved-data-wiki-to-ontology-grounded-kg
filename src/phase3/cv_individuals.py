#!/usr/bin/env python3
"""
Phase 3 - Module: controlled-vocabulary individuals (CV typing).

Types every vocabulary VALUE as its ontology vocabulary class, e.g.
    ed:Q425 "Adult Age Group"  ->  ed:Q425 a :AgeCategory
so record modules (AgeRecord, SexRecord, Event, ...) point :hasValue / :hasXType at
values that are already correctly typed.

Two complementary mechanisms:
  VOCAB  - typing by `instance of` (edt:P1). Catches LEAF values that never appear as
           class-items in the mapping (e.g. Q425). For each vocabulary BOTH the wiki
           CV container and the value-class Q are listed against the same ontology
           class - whichever the values actually hang off will match, the other is a
           harmless no-op.
  DIRECT - explicit value items from the CV_INDIVIDUAL bucket, typed unconditionally.
           Belt-and-braces: guarantees these are typed even if their instance-of link
           is missing. RDF is a set, so overlap with VOCAB costs nothing.

Usage (from repo root):
    python phase3\\cv_individuals.py --dataset Enslaved-dataset
    python phase3\\cv_individuals.py --print-query        # show SPARQL, don't run
Writes out/phase3/cv_individuals.ttl. Standard library only.
"""

import argparse
import os
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import OUT_PHASE3, ensure  # noqa: E402

# ---------------------------------------------------------------------------
# VOCAB: wiki Q (CV container OR value-class)  ->  ontology vocabulary class
# ---------------------------------------------------------------------------
VOCAB = {
    # Age
    "Q219": ":AgeCategory",                  # CV for Age Category
    "Q412": ":AgeCategory",                  # Age Category  (confirmed: types Q425)
    # Sex
    "Q86":  ":SexTypes",                     # CV for Sex
    "Q291": ":SexTypes",                     # Sex
    # Event type
    "Q139": ":EventTypes",                   # CV for Event Type
    "Q282": ":EventTypes",                   # Event Type
    # Place type
    "Q205": ":PlaceTypeCV",                  # CV for Place Type
    "Q288": ":PlaceTypeCV",                  # Place Type
    # Document type
    "Q360": ":DocumentTypes",                # CV for Document Type
    "Q122": ":DocumentTypes",                # Document Type
    # Occupation
    "Q408": ":Occupations",                  # CV for Occupation
    "Q108": ":Occupations",                  # Occupation
    # Person status
    "Q204": ":PSCategories",                 # CV for Person Status
    "Q375": ":PSCategories",                 # Person Status
    # Inter-agent relationship
    "Q457": ":InterAgentRelationshipTypes",  # CV for Inter Agent Relationship
    # Place controlled vocabularies (regional schemes)
    "Q436": ":PlaceCV",                      # Freedom Narratives Region
    "Q437": ":PlaceCV",                      # Slave Voyages Region
    # Participant role   (target of P17 hasParticipantRole -> :hasParticipantRoleType)
    "Q351": ":ParticipantRoleTypes",         # CV for Role
    "Q316": ":ParticipantRoleTypes",         # Role in a Life Event
    # Ethnonyms          (target of P46 hasEthnolinguisticDescriptor -> :hasDescriptiveEthnonym)
    "Q422": ":ECVO",                         # CV for Ethnonyms
    "Q298": ":ECVO",                         # Ethnolinguistic Descriptor
    # License information
    "Q433": ":LicenseInformation",           # CV for License Information (P15 value target)
}

# ---------------------------------------------------------------------------
# DIRECT: specific value ITEMS typed unconditionally (from the CV_INDIVIDUAL bucket)
# ---------------------------------------------------------------------------
DIRECT = {
    # Match values
    "Q624608": ":MatchType",   # Close Match
    "Q624609": ":MatchType",   # No Match
    # Event-type values
    "Q146": ":EventTypes",     # Voyage
    "Q147": ":EventTypes",     # Birth
    "Q148": ":EventTypes",     # Death
    "Q149": ":EventTypes",     # Baptism or Naming Ceremony
    "Q150": ":EventTypes",     # Marriage
    "Q151": ":EventTypes",     # Enslavement
    "Q153": ":EventTypes",     # Sale or Transfer
    "Q154": ":EventTypes",     # Disappearance
    "Q155": ":EventTypes",     # Legal Proceeding
    "Q157": ":EventTypes",     # Narrative
    "Q158": ":EventTypes",     # Health or Sickness or Injury
    "Q159": ":EventTypes",     # Residence
    "Q161": ":EventTypes",     # Relocation
    "Q163": ":EventTypes",     # Family Separation
    "Q164": ":EventTypes",     # Military Service
    "Q250": ":EventTypes",     # Registration
    "Q281": ":EventTypes",     # Emancipation or Manumission
    "Q473": ":EventTypes",     # Membership
    "Q10087": ":EventTypes",   # Embarkation
    "Q10088": ":EventTypes",   # Disembarkation
    "Q298746": ":EventTypes",  # Mortgage
    "Q647904": ":EventTypes",  # Appraisal
    "Q856060": ":EventTypes",  # Mention
    "Q907443": ":EventTypes",  # Advertisement
    # Ethnonym VALUES typed as Place (Q301) in the dump but USED as P46 ethnolinguistic descriptors
    # (:hasECVO values in OriginRecord) - dual-role place-peoples. DIRECT-typed :ECVO so the origin
    # module's :hasECVO targets are all typed (closes origin_record V3e = 2 dangling); they KEEP their
    # :Place typing too (additive - RDF is a set - so any place-of-origin use is unaffected). This is
    # faithful to the source's P46 use, not a reclassification of the person's fact. Reversible: drop
    # these two lines to instead log the 157 records as an accepted :hasECVO-untyped coverage gap.
    "Q9965": ":ECVO",          # Sherbro   (Place + used as a P46 ethnonym; 156 uses)
    "Q647859": ":ECVO",        # Caribbean (Place + used as a P46 ethnonym; 1 use)
}


# ---------------------------------------------------------------------------
# LABELS - carried inline so each module labels exactly the entities it emits.
# A separate labels module can't know which entities survive without duplicating
# every module's selection logic. Edit LANG / drop a line to change policy.
# ---------------------------------------------------------------------------
LANG = "en"
LABEL_BLOCK = f"""    OPTIONAL {{ ?v rdfs:label ?label .            FILTER(lang(?label) = "{LANG}") }}
    OPTIONAL {{ ?v skos:altLabel ?altLabel .      FILTER(lang(?altLabel) = "{LANG}") }}
    OPTIONAL {{ ?v schema:description ?description . FILTER(lang(?description) = "{LANG}") }}"""


def build_query() -> str:
    blocks = []
    if VOCAB:
        rows = "\n".join(f"            (ed:{q} {t})" for q, t in VOCAB.items())
        blocks.append(
            "    {\n"
            "        VALUES (?cvClass ?type) {\n"
            f"{rows}\n"
            "        }\n"
            "        ?v edt:P1 ?cvClass .\n"
            "    }"
        )
    if DIRECT:
        rows = "\n".join(f"            (ed:{q} {t})" for q, t in DIRECT.items())
        blocks.append(
            "    {\n"
            "        VALUES (?v ?type) {\n"
            f"{rows}\n"
            "        }\n"
            "    }"
        )
    where = "\n    UNION\n".join(blocks)
    return (
        "PREFIX :       <https://enslaved.org/ontology/>\n"
        "PREFIX ed:     <https://lod.enslaved.org/entity/>\n"
        "PREFIX edt:    <https://lod.enslaved.org/prop/direct/>\n"
        "PREFIX rdf:    <http://www.w3.org/1999/02/22-rdf-syntax-ns#>\n"
        "PREFIX rdfs:   <http://www.w3.org/2000/01/rdf-schema#>\n"
        "PREFIX skos:   <http://www.w3.org/2004/02/skos/core#>\n"
        "PREFIX schema: <http://schema.org/>\n\n"
        "CONSTRUCT {\n"
        "    ?v a ?type ;\n"
        "       rdfs:label ?label ;\n"
        "       skos:altLabel ?altLabel ;\n"
        "       schema:description ?description .\n"
        "}\n"
        "WHERE {\n"
        f"{where}\n"
        f"{LABEL_BLOCK}\n"
        "}"
    )


def run_construct(endpoint: str, query: str) -> str:
    data = urllib.parse.urlencode({"query": query}).encode("utf-8")
    req = urllib.request.Request(
        endpoint, data=data,
        headers={"Accept": "text/turtle", "Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req) as resp:
        return resp.read().decode("utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Phase 3 CV-individuals CONSTRUCT.")
    ap.add_argument("--server", default="http://localhost:3030")
    ap.add_argument("--dataset", default="Enslaved-dataset")
    ap.add_argument("--out", default=None)
    ap.add_argument("--print-query", action="store_true", help="print generated SPARQL and exit")
    args = ap.parse_args()

    query = build_query()
    if args.print_query:
        print(query)
        return 0

    endpoint = f"{args.server.rstrip('/')}/{args.dataset}/query"
    out_path = args.out or os.path.join(ensure(OUT_PHASE3), "cv_individuals.ttl")

    vocab_classes = sorted(set(VOCAB.values()) | set(DIRECT.values()))
    print(f"Querying {endpoint}")
    print(f"  {len(VOCAB)} instance-of keys + {len(DIRECT)} direct values "
          f"-> {len(vocab_classes)} vocabulary classes: {', '.join(vocab_classes)}")

    ttl = run_construct(endpoint, query)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(ttl)

    triples = sum(1 for ln in ttl.splitlines()
                  if ln.strip().endswith(" .") and not ln.strip().startswith(("@", "#")))
    print(f"wrote {out_path}  (~{triples} typed values)")
    print("Checks: ed:Q425 should appear as :AgeCategory (closes the AgeRecord loop).")
    print("If a vocabulary yields nothing, its values hang off a Q not listed in VOCAB.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
