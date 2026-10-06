#!/usr/bin/env python3
"""
Phase 3 - :Agent -> :Person / :Organization, plus every Agent-owned edge re-homed from the
self-contained record modules.

Key points (see agent-module notes / MODULE-MAP for the full rationale):
  * Each owning edge re-derives its record module's per-attestation IRI byte-for-byte:
    via-reified records   <stmt>-<event|noEvent>-<source|noSource>
    inter-agent records   <stmt>-<event|noEvent>-<source|noSource>-<to>
    participant roles     <stmt>-<agent>-<source|noSource>
    description / extref  <agent>-desc-<md5(text)> / <agent>-extref-<md5(url)>
  * AGENT GUARD (edt:P1 Q410|Q411) lives in ENUMERATE only; records on untyped subjects stay
    ownerless (D-AG-5), so an edge count can sit a hair below its module's V1.
  * :Agent is not asserted (subclass-inferred). :hasExternalReference is expected 0.
  * :hasParticipantRoleRecord IS materialised (reverses D-AG-3): its inverse :roleProvidedBy only
    yields it under a reasoner, which this store is not served with. Pass --pr-events-only when
    participant_role.ttl was built with --events-only, so edges match that record subset.
  * Per agent chunk, every block runs as its own CONSTRUCT (N-Triples); the results are merged
    so each agent is written ONCE with all its triples, as prefixed Turtle.
  * Deprecated statements are excluded with MINUS, not FILTER NOT EXISTS: Jena pushes the filter
    into the middle of a multi-triple pattern, and on an empty split Jena 6.0.0 TDB2 fails with
    "Peek iterator is already empty" (GH-3751).

Usage: python src/phase3/agent.py --dataset Enslaved-dataset [--block NAME] [--chunk-size N]
       [--limit N] [--iri ed:Qxxx] [--print-query]   ->  out/phase3/agent.ttl
"""

import argparse
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import OUT_PHASE3, ensure  # noqa: E402

ENTITY_NS = "https://lod.enslaved.org/entity/"

# A Person carrying P20/P31/P32/P22/P33 statements, for --iri shape checks.
TEST_ENTITY = "ed:Q1124931"

PREFIXES = """PREFIX :        <https://enslaved.org/ontology/>
PREFIX ed:      <https://lod.enslaved.org/entity/>
PREFIX edt:     <https://lod.enslaved.org/prop/direct/>
PREFIX ep:      <https://lod.enslaved.org/prop/>
PREFIX eps:     <https://lod.enslaved.org/prop/statement/>
PREFIX pq:      <https://lod.enslaved.org/prop/qualifier/>
PREFIX epr:     <https://lod.enslaved.org/prop/reference/>
PREFIX prov:    <http://www.w3.org/ns/prov#>
PREFIX wikibase:<http://wikiba.se/ontology#>
PREFIX rdfs:    <http://www.w3.org/2000/01/rdf-schema#>
"""

# Prefixes for the written Turtle. eds: must be listed before ed: so the longer namespace wins.
OUTPUT_PREFIXES = [
    ("", "https://enslaved.org/ontology/"),
    ("eds", "https://lod.enslaved.org/entity/statement/"),
    ("ed", "https://lod.enslaved.org/entity/"),
    ("rdf", "http://www.w3.org/1999/02/22-rdf-syntax-ns#"),
    ("rdfs", "http://www.w3.org/2000/01/rdf-schema#"),
]

# Conservative Turtle PN_LOCAL: anything outside it is written as a full <IRI> instead.
SAFE_LOCAL_NAME = re.compile(r"[A-Za-z0-9_](?:[A-Za-z0-9_.-]*[A-Za-z0-9_-])?")

ENUMERATE = PREFIXES + """
SELECT DISTINCT ?agent WHERE {{
    {agent_values}
    VALUES ?agentClass {{ ed:Q410 ed:Q411 }}
    ?agent edt:P1 ?agentClass .
}}
"""

CONSTRUCT = PREFIXES + """
CONSTRUCT {{ ?agent {predicate} ?target . }}
WHERE {{
    VALUES ?agent {{ {values} }}
    {pattern}
}}
"""


@dataclass(frozen=True)
class Block:
    """One kind of emitted triple: ?agent <predicate> ?target, with ?target bound by pattern."""
    predicate: str
    pattern: str


def attested_record(predicate: str, prop: str, required: str = "", key_suffix: str = "") -> Block:
    """Block whose ?target is the record IRI a via-reification module mints for ep:<prop>.

    Mirrors that module's subject selection (same required triples, deprecated rank excluded)
    and its per-(event, source) split, so each edge lands on an emitted record.
    """
    record_key = (
        f'"-", COALESCE(STRAFTER(STR(?event), "https://lod.enslaved.org/entity/"), "noEvent"), '
        f'"-", COALESCE(STRAFTER(STR(?source), "https://lod.enslaved.org/entity/"), "noSource")'
    )
    required_line = f"\n    {required}" if required else ""
    return Block(predicate, f"""?agent ep:{prop} ?stmt .{required_line}
    MINUS {{ ?stmt wikibase:rank wikibase:DeprecatedRank }}
    OPTIONAL {{ ?stmt pq:P18 ?event . }}
    OPTIONAL {{ ?stmt prov:wasDerivedFrom ?ref . ?ref epr:P6 ?source . }}
    BIND(IRI(CONCAT(STR(?stmt), {record_key}{key_suffix})) AS ?target)""")


def participant_role_record() -> Block:
    """Block whose ?target is the record IRI participant_role.py mints: <stmt>-<agent>-<source>.

    Here the agent is a pq:P17 qualifier on a provider's ep:P29 statement (not the statement's
    subject), and the record is split per (agent, source) with no event part. The role-value
    class guard and the optional Event-only provider guard mirror that module's ENUMERATE.
    VALUES leads the group so the multi-triple pattern never starts from empty input.
    """
    return Block(":hasParticipantRoleRecord", f"""VALUES ?roleTypeClass {{ ed:Q316 ed:Q351 }}
    ?stmt pq:P17 ?agent .
    ?provider ep:P29 ?stmt .
    ?stmt eps:P29 ?roleType .
    ?roleType edt:P1 ?roleTypeClass .
    MINUS {{ ?stmt wikibase:rank wikibase:DeprecatedRank }}
    OPTIONAL {{ ?stmt prov:wasDerivedFrom ?ref . ?ref epr:P6 ?source . }}
    BIND(IRI(CONCAT(
        STR(?stmt),
        "-", STRAFTER(STR(?agent), "{ENTITY_NS}"),
        "-", COALESCE(STRAFTER(STR(?source), "{ENTITY_NS}"), "noSource")
    )) AS ?target)""")


def minted_node(predicate: str, prop: str, tag: str) -> Block:
    """Block whose ?target is a synthesis module's <agent>-<tag>-<md5(value)> node."""
    return Block(predicate, f"""?agent edt:{prop} ?value .
    BIND(IRI(CONCAT(STR(?agent), "-{tag}-", MD5(STR(?value)))) AS ?target)""")


# Order = predicate order within each agent's Turtle block.
BLOCKS = {
    "types": Block("a", """VALUES ?agentClass { ed:Q410 ed:Q411 }
    ?agent edt:P1 ?agentClass .
    BIND(IF(?agentClass = ed:Q411, :Organization, :Person) AS ?target)"""),
    "label": Block("rdfs:label", '?agent rdfs:label ?target . FILTER(LANG(?target) = "en")'),
    "hasNameRecord":         attested_record(":hasNameRecord", "P20", "?stmt eps:P20 ?fullName ."),
    "hasAgeRecord":          attested_record(":hasAgeRecord", "P42"),
    "hasSexRecord":          attested_record(":hasSexRecord", "P31"),
    "hasRaceRecord":         attested_record(":hasRaceRecord", "P32"),
    "hasOccupationRecord":   attested_record(":hasOccupationRecord", "P22"),
    "hasPersonStatusRecord": attested_record(":hasPersonStatusRecord", "P33"),
    "hasOriginRecord":       attested_record(":hasOriginRecord", "P46"),
    # :isRelationshipFrom is NOT the inverse of this edge (D-IAR-4), so it must be asserted here.
    # pq:P40 is required and split on, exactly as inter_agent_relationship.py does.
    "hasInterAgentRelationshipRecord": attested_record(
        ":hasInterAgentRelationshipRecord", "P39",
        "?stmt eps:P39 ?relType .\n    ?stmt pq:P40 ?to .",
        f', "-", STRAFTER(STR(?to), "{ENTITY_NS}")',
    ),
    "hasParticipantRoleRecord": participant_role_record(),
    "hasDescriptionText":  minted_node(":hasDescriptionText", "P66", "desc"),
    "hasExternalReference": minted_node(":hasExternalReference", "P21", "extref"),
}


def build_enumerate(iri, limit) -> str:
    """Build the agent ENUMERATE query, optionally pinned to one agent (--iri) and LIMITed."""
    agent_values = f"VALUES ?agent {{ {iri} }}" if iri else ""
    return ENUMERATE.format(agent_values=agent_values) + (f"LIMIT {limit}\n" if limit else "")


def build_construct(block: Block, agents) -> str:
    """Build one block's CONSTRUCT scoped to a chunk of agent IRIs via VALUES ?agent."""
    values = " ".join(f"<{a}>" for a in agents)
    return CONSTRUCT.format(predicate=block.predicate, pattern=block.pattern, values=values)


def post(endpoint: str, query: str, accept: str) -> str:
    """POST a SPARQL query and return the response body as text."""
    data = urllib.parse.urlencode({"query": query}).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=data,
        headers={"Accept": accept, "Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req) as resp:
        return resp.read().decode("utf-8")


def enumerate_agents(endpoint: str, iri, limit) -> list:
    """Fetch the distinct Q410/Q411 agent IRIs, in the order every chunk is written."""
    rows = post(endpoint, build_enumerate(iri, limit), "text/tab-separated-values").splitlines()[1:]
    return [r[1:-1] for r in rows if r.startswith("<") and r.endswith(">")]


def parse_ntriples(nt: str):
    """Yield (subject, predicate, object) terms from N-Triples, each still in N-Triples syntax.

    Subjects and predicates here are always IRIs (no spaces), so the object is whatever
    remains before the closing ' .' - including literals that contain spaces.
    """
    for line in nt.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        subject, predicate, rest = line.split(" ", 2)
        yield subject, predicate, rest[:-1].rstrip()


def turtle_term(term: str) -> str:
    """Abbreviate an N-Triples IRI to a prefixed name where safe; literals pass through unchanged."""
    if not (term.startswith("<") and term.endswith(">")):
        return term
    iri = term[1:-1]
    for prefix, namespace in OUTPUT_PREFIXES:
        if iri.startswith(namespace) and SAFE_LOCAL_NAME.fullmatch(iri[len(namespace):]):
            return f"{prefix}:{iri[len(namespace):]}"
    return term


def turtle_header() -> str:
    """The file's single @prefix block."""
    return "".join(f"@prefix {p}: <{ns}> .\n" for p, ns in OUTPUT_PREFIXES) + "\n"


def turtle_subject_block(subject: str, predicates: dict) -> str:
    """One agent's Turtle statement: every predicate on its own line, objects comma-separated.

    Objects are sorted so a statement's attestations sit together and reruns diff cleanly.
    """
    lines = [f"{turtle_term(p)}  {' , '.join(sorted(turtle_term(o) for o in objs))}"
             for p, objs in predicates.items()]
    return f"{turtle_term(subject)}  " + " ;\n    ".join(lines) + " .\n\n"


def construct_chunk(endpoint: str, blocks: dict, agents, counts: dict) -> dict:
    """Run every selected block for one agent chunk; return {agent: {predicate: [objects]}}.

    Predicates keep block order and objects keep first-seen order, deduplicated.
    """
    merged = {}
    for name, block in blocks.items():
        try:
            nt = post(endpoint, build_construct(block, agents), "application/n-triples")
        except urllib.error.HTTPError as err:
            detail = err.read().decode("utf-8", errors="replace")[:500]
            raise SystemExit(f"\nblock {name} failed on agents {agents[0]} ..: HTTP {err.code}\n{detail}")
        for subject, predicate, obj in parse_ntriples(nt):
            objects = merged.setdefault(subject, {}).setdefault(predicate, [])
            if obj not in objects:
                objects.append(obj)
                counts[name] += 1
    return merged


def run(server: str, dataset: str, blocks: dict, chunk_size: int, iri, limit, out_path: str) -> None:
    """Enumerate agents, build each chunk's merged triples, and write one Turtle block per agent."""
    endpoint = f"{server.rstrip('/')}/{dataset}/query"
    scope = f" (agent {iri})" if iri else ""
    print(f"Enumerating Q410/Q411 agents at {endpoint}{scope} ...")
    try:
        agents = enumerate_agents(endpoint, iri, limit)
    except urllib.error.URLError as err:
        raise SystemExit(f"cannot reach {endpoint}: {err}")
    if not agents:
        raise SystemExit("no Q410/Q411 agents matched - check --dataset / --iri")

    chunks = [agents[i:i + chunk_size] for i in range(0, len(agents), chunk_size)]
    print(f"  {len(agents):,} agents; {chunk_size}/chunk -> {len(chunks)} chunks x {len(blocks)} blocks")

    counts = {name: 0 for name in blocks}
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(turtle_header())
        for i, chunk in enumerate(chunks, 1):
            merged = construct_chunk(endpoint, blocks, chunk, counts)
            for agent in chunk:
                predicates = merged.get(f"<{agent}>")
                if predicates:
                    fh.write(turtle_subject_block(f"<{agent}>", predicates))
            print(f"\r  chunk {i}/{len(chunks)}  {sum(counts.values()):,} triples", end="", flush=True)
    print()

    print(f"\nwrote {out_path}  ({sum(counts.values()):,} triples, {os.path.getsize(out_path):,} bytes)")
    for name, n in counts.items():
        print(f"  {name:<34}{n:>12,}")
    print("Owning-edge counts should equal (or sit just under, D-AG-5) each record module's V1;")
    print("hasExternalReference == 0 is correct. Verify with agent_diagnostics.py --phase after.")

    if iri:
        print("\n--- shape check ---")
        with open(out_path, encoding="utf-8") as fh:
            print(fh.read(), end="")


def main() -> int:
    """Parse CLI arguments and either print the generated SPARQL or run the chunked build."""
    ap = argparse.ArgumentParser(
        description="Phase 3 :Agent builder - type, label and all re-homed owning edges, "
                    "chunked by agent and written one Turtle block per agent.")
    ap.add_argument("--server", default="http://localhost:3030")
    ap.add_argument("--dataset", default="Enslaved-dataset")
    ap.add_argument("--block", default="all", choices=["all", *BLOCKS],
                    help="emit one kind of triple only (default: all)")
    ap.add_argument("--chunk-size", type=int, default=1000, help="agents per chunk")
    ap.add_argument("--iri", default=None,
                    help=f"scope to one agent IRI for a shape check (e.g. {TEST_ENTITY})")
    ap.add_argument("--limit", type=int, default=None, help="cap agents enumerated (smoke-test)")
    ap.add_argument("--out", default=None, help="output path (default out/phase3/agent.ttl)")
    ap.add_argument("--print-query", action="store_true", help="print generated SPARQL and exit")
    args = ap.parse_args()

    names = list(BLOCKS) if args.block == "all" else [args.block]
    blocks = {name: BLOCKS[name] for name in names}

    if args.print_query:
        print(build_enumerate(args.iri, args.limit))
        for name, block in blocks.items():
            print(f"# --- {name} ---")
            print(build_construct(block, [f"{ENTITY_NS}EXAMPLE"]))
        return 0

    if args.chunk_size < 1:
        raise SystemExit("--chunk-size must be >= 1")

    out_path = args.out or os.path.join(ensure(OUT_PHASE3), "agent.ttl")
    run(args.server, args.dataset, blocks, args.chunk_size, args.iri, args.limit, out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
