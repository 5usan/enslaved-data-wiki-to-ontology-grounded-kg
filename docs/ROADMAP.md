# Wiki-based KG → Ontology-grounded KG — Roadmap

**Goal:** Convert the Enslaved.org Wikibase RDF dump (`data/raw/chunks/`) into a graph expressed
in the Enslaved Ontology (`ontology/enslaved-v2.ttl`), using SPARQL `CONSTRUCT` queries run with
Apache Jena.

**Working mode:** Guided. Claude scaffolds each query and explains the reasoning; *you*
write the SPARQL; Claude reviews and runs it against the real data.

---

## The core idea (one record)

The subject IRI is **preserved** — you re-type and re-label an entity, you don't mint a
new one. Example record `ed:Q2 "Age 18"`:

| Wiki-based (opaque)                    | Ontology-grounded                       |
|----------------------------------------|-----------------------------------------|
| `ed:Q2 a wikibase:Item`                | `ed:Q2 a :AgeRecord`                    |
| `edt:P1 ed:Q424`  ("instance of" → "Age Record") | *(becomes the rdf:type above)* |
| `edt:P3 "+18"`  ("hasAgeValue")        | `:hasAgeValue "+18"^^xsd:decimal`       |
| `edt:P4 ed:Q425`  ("hasAgeCategory")   | `:hasAgeCategory ed:Q425`               |
|                                        | `ed:Q425 a :AgeCategory`                |

Every CONSTRUCT is built from **three move types**:
1. **Typing** — `instance of <classItem>` ⟹ `rdf:type :OntologyClass`
2. **Property rename** — opaque `edt:Pxx` ⟹ named ontology property (via the mapping)
3. **De-reification** — keep the direct `edt:` triples; drop the `wikibase:Statement`
   scaffolding (`ep:`, `eps:`, `epq:`, ...).

---

## Phases

### Phase 0 — Tooling & fast iteration slice
Install Jena (`riot`, `arq`, `shacl`). Carve a small definitions-only slice out of
`data/raw/chunks/chunk_0.ttl` so query iteration takes seconds, not minutes.

### Phase 1 — Extract the mapping
SPARQL over the dump to list every `ed:Pxxx` (label + `wikibase:propertyType`) and every
`ed:Qxxx` used as a class. **This table drives everything downstream.**

### Phase 2 — Reconcile against the ontology
Match each wiki label to a class/property in `ontology/enslaved-v2.ttl`.
- Labels with **no ontology home** → manual decisions.
- Ontology terms with **no wiki source** → coverage gaps.

### Phase 3 — One CONSTRUCT per ontology module
Module by module (AgeRecord → Person → Place → Event → …), write a CONSTRUCT that types,
renames, and de-reifies. You write; Claude reviews.

### Phase 4 — Run over all chunks & merge
Execute the CONSTRUCT set across all 22 chunks; merge into one ontology-grounded TTL.

### Phase 5 — Validate
Run SHACL / reasoning to confirm every entity has a valid ontology type and properties
respect their domains and ranges.

---

## Known facts about the data
- 22 chunks, ~3.4 GB total; `data/raw/chunks/chunk_0.ttl` alone ≈ 162 MB / 4.9M lines.
- `chunk_0` declares 73 `wikibase:Property` definitions, each with an `rdfs:label`.
- Property labels are already ontology-flavored (`hasAgeValue`, `locatedIn`, …) — the
  wiki KG was almost certainly generated *from* this ontology, so the mapping is largely
  recoverable rather than invented.
- Ontology: 46 classes, 52 object properties, 19 datatype properties.
