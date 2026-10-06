#!/usr/bin/env python3
"""
Phase 3 - Module: :ResearchProject   (source class ed:Q172)

Runs ONE SPARQL CONSTRUCT against Fuseki and writes the ontology-grounded triples as Turtle.

:ResearchProject rdfs:subClassOf :Event , :ProvenanceActivity, so a Q172 item is an Event and a
ProvenanceActivity by entailment. This module types ONLY :ResearchProject and lets the two supers
be inferred - the same convention the Agent module uses (type :Person/:Organization, :Agent
inferred). Nothing asserts `?rp a :Event`; a reasoner entails it, and a non-reasoning consumer can
materialise the subclass axioms once, globally.

WHAT THIS MODULE OWNS
---------------------
The four ResearchProject-native classes (MODULE-MAP): :ResearchProject :Researcher
:ResearchProjectPIRole :ResearchProjectContributorRole. Plus, for the Q172 subjects, the
Event-native own-facts that apply and the satellite links native to ResearchProject:

  A. CORE        type + :hasName (+rdfs:label, from P20) + :atPlace (P27) + reflexive
                 :eventSelfProperty. :hasEventType (P30) renamed if present - expected ~0 (D-RP-3).
  B. TEMPORAL    :hasTemporalExtent -> temporal_extent.py's <rp>-extent      (edt:P28 / edt:P63)
  C. DESCRIPTION :hasDescriptionText -> description.py's <rp>-desc-<md5(text)>    (edt:P66)
  D. EXTREF      :hasExternalReference -> external_reference.py's <rp>-extref-<md5(url)> (edt:P21)
  E. PI          :providesParticipantRole -> the PI agent, typed :ResearchProjectPIRole  (edt:P14)
  F. CONTRIBUTOR :providesParticipantRole -> minted :ResearchProjectContributorRole      (edt:P13)

Like event.py, B/C/D re-derive each satellite module's deterministic IRI with the IDENTICAL bind,
so the emitted link always lands on a node the satellite actually minted and re-runs are idempotent.

THE RESEARCHER ROLE STRUCTURE - resolves P13/P14 from the mapping DROP bucket
-----------------------------------------------------------------------------
Both P13 (hasContributor) and P14 (hasPI) sit in the mapping's DROP / "needs decision" bucket.
This module is where that decision is settled; run research_project_diagnostics.rq queries 3-4
FIRST to confirm the source shape before accepting the full run.

D-RP-1 - PI (P14, WikibaseItem -> an agent). DEAD DIRECTION: diagnostic 3 (2026-09-08) found
  edt:P14 has ZERO instances dump-wide (no rows), exactly like P19 roleProvidedBy. So
  :ResearchProjectPIRole gets NO instances from the source and stays empty. The branch is kept,
  expected-0, so the bind is ready if P14 ever gains data - mirroring event.py keeping its edt:P21
  branch for events. The intended shape, had the data existed: type the PI AGENT itself
  :ResearchProjectPIRole and link by :providesParticipantRole - role-as-class-on-agent, exactly the
  idiom the ontology uses for :Person/:Organization on an :Agent, no node minted (re-type, never
  re-mint). The inverse-providesParticipantRole allValuesFrom :ResearchProject restriction on
  :ResearchProjectPIRole would hold by construction (the agent is the object of a ResearchProject's
  providesParticipantRole). Considered and rejected: minting a stand-in role node per (project,
  agent) like ParticipantRoleRecord - but :roleProvidedBy (record -> agent) is native to
  :ParticipantRoleRecord, NOT to :Researcher, so a minted node would have no ontology property to
  reach its agent. Typing the agent directly is the only lossless option.

D-RP-2 - Contributor (P13, String -> no agent IRI). A node MUST be minted:
  <rp>-contributor-<md5(name)> a :ResearchProjectContributorRole, with the contributor name on
  rdfs:label. :Researcher has no name datatype property, and :hasName is native to
  Event/Place/ResearchProject but NOT to :Researcher, so rdfs:label is the honest carrier - not
  :hasName on a Researcher. md5-per-name discriminates a project's several contributors into several
  nodes rather than one node collecting many labels (diagnostic 4b sizes the multi-contributor case);
  the md5 folds in ?rp, so a node belongs to one project by construction.

Both role classes are rdfs:subClassOf :Researcher, so :Researcher is inferred, never re-asserted.

D-RP-3 - :hasEventType card-1 is an ACCEPTED GAP. :ResearchProject inherits :Event's
  `hasEventType qualifiedCardinality 1 onClass :EventTypes`, but a research project is not a
  life-event and the source supplies no P30 for Q172 (diagnostic 2 confirmed 0). The rename branch
  is kept so a project that ever gains a P30 is handled, but nothing is fabricated to satisfy the
  cardinality - a visible gap beats an invented value (the project's standing rule). Phase 5 SHACL
  surfaces it. :atPlace (P27) is likewise absent for every project. NOTE :hasName is NOT a gap -
  diagnostic 2 found P20 on all 41 projects, so Event's hasName min-1 is fully satisfied.
  :hasTemporalExtent card-1 has one likely gap: ~40 of 41 projects are dated (39 P63 + 3 P28,
  overlapping), so the ~1 undated project has no extent - accepted, not fabricated.

DIAGNOSTIC FINDINGS (research_project_diagnostics.rq, run 2026-09-08 against the full dump):
  41 Q172 projects, 0 deprecated. Coverage: P20 41/41, P66 40, P13 40 (65 string claims, up to 5
  contributors/project), P63 39, P21 29, P28 3. ABSENT on all projects: P30, P27, P14, and all of
  P15/P16/P6/P23/P25/P26 (no EntityWithProvenance facts on Q172). Expected output: 41
  :ResearchProject, ~40 :hasTemporalExtent (temporal_extent EO branch covers the P63-only ones),
  ~45 :hasDescriptionText, ~67 :hasExternalReference, ~65 :ResearchProjectContributorRole, 0
  :ResearchProjectPIRole (D-RP-1 dead direction).

D-RP-4 - INHERITED-RESTRICTION TENSION, flagged not papered over. The owl:Thing restriction
  `providesParticipantRole allValuesFrom :ParticipantRoleRecord` is global, yet the Researcher-role
  classes carry an explicit `[inverseOf providesParticipantRole] allValuesFrom :ResearchProject` -
  the ontology authors clearly intend providesParticipantRole to link a ResearchProject to its
  Researchers (else the two dedicated classes have no reason to exist). Using it means a reasoner
  also infers the researcher nodes as :ParticipantRoleRecord: a latent :Researcher /
  :ParticipantRoleRecord overlap. That is an ontology question for Phase 5, not one to resolve by
  inventing a different edge. :performedBy (from :ProvenanceActivity, allValuesFrom :Agent) was
  weighed as the PI home and rejected for the same reason - the dedicated :ResearchProjectPIRole
  class exists precisely to be the providesParticipantRole target.

WHY UNION, NOT OPTIONAL (inherited from event.py, 2026-09-06)
-------------------------------------------------------------
Parallel OPTIONAL blocks over a multi-triple pattern trip a TDB2 optimizer bug
(ARQInternalErrorException "Peek iterator is already empty", HTTP 500). Each concern is its own
top-level UNION branch, every branch TYPE-guarded on `?rp edt:P1 ed:Q172`; the CORE branch alone
guarantees a link-less project still types. Branches bind only their own link variable, so the
multi-valued links never cross-produce. `?rp a :ResearchProject` / `:eventSelfProperty` re-emit
per branch and dedup (CONSTRUCT stores a set).

Usage (from repo root):
    python src/phase3/research_project.py --dataset Enslaved-dataset               # full run
    python src/phase3/research_project.py --dataset Enslaved-dataset --test --iri ed:Q...  # one project
    python src/phase3/research_project.py --dataset Enslaved-dataset --limit 1000  # smoke-test a slice
    python src/phase3/research_project.py --print-query                            # SPARQL only
Writes out/phase3/research_project.ttl. Standard library only.
"""

import argparse
import os
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import OUT_PHASE3, ensure  # noqa: E402

# There is no hard-coded canonical Q172 IRI in the dump notes - pick a real one from
# research_project_diagnostics.rq query 1 and pass it with --iri for a shape check. The default is
# a placeholder that returns 0 rows (harmless) until overridden.
TEST_PROJECT = "ed:Q172-REPLACE-WITH-A-REAL-PROJECT"

# __VALUES__ / __LIMIT__ are filled by str.replace (not .format) so a literal { } in a comment can
# never be misread as a format field.
CONSTRUCT = """
PREFIX :        <https://enslaved.org/ontology/>
PREFIX ed:      <https://lod.enslaved.org/entity/>
PREFIX edt:     <https://lod.enslaved.org/prop/direct/>
PREFIX wikibase:<http://wikiba.se/ontology#>
PREFIX rdfs:    <http://www.w3.org/2000/01/rdf-schema#>

CONSTRUCT {
    ?rp  a  :ResearchProject ;
         :hasName                 ?name ;
         rdfs:label               ?name ;
         :hasEventType            ?type ;
         :atPlace                 ?place ;
         :eventSelfProperty       ?rp ;
         :hasTemporalExtent       ?temporalExtent ;
         :hasDescriptionText      ?desc ;
         :hasExternalReference    ?externalReference ;
         :providesParticipantRole ?participant .

    ?pi  a  :ResearchProjectPIRole .

    ?contributor a  :ResearchProjectContributorRole ;
                 rdfs:label ?contributorName .
}
WHERE {
    __VALUES__
    {
        # --- CORE: type + Event-native own-facts (type + renames + reflexive self-edge) --------
        ?rp edt:P1 ed:Q172 .
        FILTER NOT EXISTS { ?rp wikibase:rank wikibase:DeprecatedRank }
        OPTIONAL { ?rp edt:P20 ?name  }                # hasName (+label) - Event min-1
        OPTIONAL { ?rp edt:P30 ?type  }                # hasEventType - inherited card-1, expect ~0 (D-RP-3)
        OPTIONAL { ?rp edt:P27 ?place }                # atPlace - if the project states one
    }
    UNION
    {
        # --- TEMPORAL: :hasTemporalExtent -> temporal_extent.py's <rp>-extent -------------------
        ?rp edt:P1 ed:Q172 .
        { ?rp edt:P28 ?extentDate } UNION { ?rp edt:P63 ?extentDate }
        BIND(IRI(CONCAT(STR(?rp), "-extent")) AS ?temporalExtent)
    }
    UNION
    {
        # --- DESCRIPTION: :hasDescriptionText -> description.py's <rp>-desc-<md5(text)> ---------
        ?rp edt:P1 ed:Q172 .
        ?rp edt:P66 ?text .
        BIND(IRI(CONCAT(STR(?rp), "-desc-", MD5(STR(?text)))) AS ?desc)
    }
    UNION
    {
        # --- EXTREF: :hasExternalReference -> external_reference.py's <rp>-extref-<md5(url)> ----
        # Unlike Event (0 carriers), ResearchProject genuinely carries P21 (source-check: 29 Q172).
        ?rp edt:P1 ed:Q172 .
        ?rp edt:P21 ?url .
        BIND(IRI(CONCAT(STR(?rp), "-extref-", MD5(STR(?url)))) AS ?externalReference)
    }
    UNION
    {
        # --- PI: providesParticipantRole -> the PI agent, typed :ResearchProjectPIRole (D-RP-1) -
        ?rp edt:P1 ed:Q172 .
        ?rp edt:P14 ?pi .
        BIND(?pi AS ?participant)
    }
    UNION
    {
        # --- CONTRIBUTOR: providesParticipantRole -> minted :ResearchProjectContributorRole (D-RP-2)
        ?rp edt:P1 ed:Q172 .
        ?rp edt:P13 ?contributorName .
        BIND(IRI(CONCAT(STR(?rp), "-contributor-", MD5(STR(?contributorName)))) AS ?contributor)
        BIND(?contributor AS ?participant)
    }
}
__LIMIT__
"""


def build_query(test: bool, iri: str, limit) -> str:
    values = f"VALUES ?rp {{ {iri} }}" if test else ""
    limit_clause = f"LIMIT {limit}" if limit else ""
    return CONSTRUCT.replace("__VALUES__", values).replace("__LIMIT__", limit_clause)


def run_construct(endpoint: str, query: str) -> str:
    """POST a CONSTRUCT query; return Turtle."""
    data = urllib.parse.urlencode({"query": query}).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=data,
        headers={
            "Accept": "text/turtle",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with urllib.request.urlopen(req) as resp:
        return resp.read().decode("utf-8")


def count_triples(ttl: str) -> int:
    """Rough triple count = ',' ';' '.' separators OUTSIDE quoted literals (multi-valued output)."""
    n = 0
    for raw in ttl.splitlines():
        s = raw.lstrip()
        if not s or s.startswith(("@", "#", "PREFIX")):
            continue
        in_quote = escaped = False
        for ch in raw:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_quote = not in_quote
            elif not in_quote and ch in ",;.":
                n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Phase 3 :ResearchProject CONSTRUCT (single query, UNION-branched) - Q172 typed "
                    ":ResearchProject plus its Event-native own-facts, the re-homed satellite links "
                    "(:hasTemporalExtent, :hasDescriptionText, :hasExternalReference) and the "
                    "Researcher role structure (:providesParticipantRole -> PI agent / contributor).")
    ap.add_argument("--server", default="http://localhost:3030")
    ap.add_argument("--dataset", default="Enslaved-dataset")
    ap.add_argument("--test", action="store_true",
                    help="restrict to a single project (--iri, from diagnostics query 1) for a shape check")
    ap.add_argument("--iri", default=TEST_PROJECT,
                    help=f"project IRI for --test (default {TEST_PROJECT} - a placeholder; override it)")
    ap.add_argument("--limit", type=int, default=None,
                    help="cap solutions (smoke-test a slice)")
    ap.add_argument("--out", default=None,
                    help="output .ttl path (default out/phase3/research_project.ttl)")
    ap.add_argument("--print-query", action="store_true", help="print generated SPARQL and exit")
    args = ap.parse_args()

    query = build_query(args.test, args.iri, args.limit)
    if args.print_query:
        print(query)
        return 0

    endpoint = f"{args.server.rstrip('/')}/{args.dataset}/query"
    out_path = args.out or os.path.join(ensure(OUT_PHASE3), "research_project.ttl")

    scope = f"TEST: {args.iri} only" if args.test else "full run"
    if args.limit:
        scope += f", LIMIT {args.limit}"
    print(f"Querying {endpoint}  ({scope})")

    ttl = run_construct(endpoint, query)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(ttl)

    print(f"wrote {out_path}  (~{count_triples(ttl)} triples)")

    if args.test:
        print(f"--- expected shape for {args.iri} (if it is a Q172) ---")
        print(f"  {args.iri} a :ResearchProject ;                 # :Event/:ProvenanceActivity inferred")
        print("      :hasName \"...\" ; rdfs:label \"...\" ;          # if P20 present (else name gap)")
        print(f"      :eventSelfProperty {args.iri} ;")
        print(f"      :hasTemporalExtent {args.iri}-extent ;       # if dated (P28/P63)")
        print(f"      :hasDescriptionText {args.iri}-desc-<md5> ;  # one per distinct P66 text")
        print(f"      :hasExternalReference {args.iri}-extref-<md5> ; # one per distinct P21 URL")
        print("      :providesParticipantRole <piAgent> , <rp>-contributor-<md5> .")
        print("  <piAgent> a :ResearchProjectPIRole .             # the P14 agent, typed - not minted")
        print("  <rp>-contributor-<md5> a :ResearchProjectContributorRole ; rdfs:label \"<name>\" .")
        print("  (:hasEventType EXPECTED absent - a project is not a life-event, D-RP-3)")
    else:
        print("Checks (run research_project_diagnostics.rq AFTER; co-load the satellite .ttls for 8):")
        print("  * :ResearchProject count == 41 (diagnostics q1)")
        print("  * every project has the reflexive :eventSelfProperty and :hasName (P20 41/41 -")
        print("    no name gap); :hasEventType and :atPlace EXPECTED 0 (D-RP-3, accepted gaps)")
        print("  * providesParticipantRole objects: ~65 :ResearchProjectContributorRole (minted,")
        print("    rdfs:label carries P13) and 0 :ResearchProjectPIRole (P14 dead direction, D-RP-1)")
        print("  * no dangling satellite links (q8b): every :hasDescriptionText/:hasExternalReference/")
        print("    :hasTemporalExtent object typed by its satellite module")
        print("")
        print("NOTE (D-RP-4): using :providesParticipantRole to reach Researchers lets a reasoner")
        print("also infer them :ParticipantRoleRecord (global owl:Thing allValuesFrom). That is a")
        print("flagged ontology overlap for Phase 5, not a bug in this module.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
