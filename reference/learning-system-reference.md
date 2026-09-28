# Learning System: Reference Template and Project Status

Project knowledge file. Consolidated from the Learning System architecture reviews (19–24 September 2026) and established external patterns. Part A shows where the project stands; Part B is the reference for building and operating the system. Update Part A whenever status changes; change Part B only when the architecture itself is revised.

**Status as of:** 24 September 2026  
**Last updated:** 25 September 2026

---

## Part A: Where we are

### A1. Summary

The core pathway works: an owner-activated procedure, derived from real incident evidence, has been delivered verbatim into a real development task, and its application has been established step by step from artifacts. Nothing yet shows that procedures are found from ordinary task vocabulary, that they change behaviour, or that they improve outcomes. The next move is to run every development task through the first-order loop, with the retrieval-vocabulary gap as the system's first internally generated learning need.

### A2. Progress along the six states

| State | Status | Basis |
|---|---|---|
| Recorded | Demonstrated | Procedure version stored with incident provenance |
| Retrieved | Partial | Storage-to-delivery pathway shown in a deterministic experiment; retrieval from ordinary task vocabulary not demonstrated |
| Delivered | Demonstrated | Delivered verbatim into a real development task |
| Applied | Demonstrated (limited) | Application of each step established from artifacts, recorded against the exact version |
| Behaviour changed | Not demonstrated | Needs a comparison (Section 8) |
| Outcome improved | Not demonstrated | Needs a controlled comparison (Section 8) |

### A3. First-order loop: stage status

| # | Stage | Status |
|---|---|---|
| 1 | Intake | Demonstrated on a real task |
| 2 | Retrieve | Gap: tasks described by domain, procedures indexed by artifact type |
| 3 | Deliver | Demonstrated, verbatim |
| 4 | Work | Demonstrated |
| 5 | Record | Demonstrated |
| 6 | Close out | Demonstrated (application judged from artifacts) |
| 7 | Consolidate | Demonstrated at least once (procedure derived from incident evidence) |
| 8 | Activate | Demonstrated (owner activation) |
| 9 | Next task | Not yet routine: every task is not yet run through the loop |

### A4. Second-order loop

Not demonstrated. Learning-event records (Section 7) should be captured from the start of routine loop operation, because they cannot be reconstructed later. To confirm: whether learning-event records are already being written.

### A5. Open issues

1. **Retrieval-vocabulary gap** (first internally generated learning need). Minimum fix: derive applicability terms mechanically from the task tags of incidents in each procedure version's provenance. Stopgap while few procedures are ACTIVE: deliver all scope statements, and record every case where a worker judges a procedure applicable but tag retrieval missed it.
2. No comparison design yet for behaviour or outcome claims (concurrent, competent baseline; counterfactual control; replicates; pre-declared metrics).
3. Evidence strength is thin: current support comes from a single project and uncontrolled cases, so ACTIVE procedures should be delivered with that label.

### A6. Next steps

1. Run every development task through the nine-stage loop in Section 3.
2. Treat the retrieval-vocabulary gap as a learning event and record it using the Section 7 fields.
3. Implement mechanical derivation of applicability terms; record misses as retrieval evidence.
4. Draft a pre-declared comparison design before making any behaviour or outcome claim.

### A7. Change log

| Date | Change |
|---|---|
| 24 Sep 2026 | Architecture reviews (19–24 Sep) consolidated into this reference |
| 25 Sep 2026 | Status section added for project knowledge |

---

## Part B: Reference

### 1. Purpose

The Learning System performs real work, learns from evidence and outcomes, keeps organisational knowledge independently of any individual AI node, applies that knowledge to later work, determines whether doing so changed behaviour or outcomes, and revises its knowledge accordingly. Eventually it should also learn which ways of learning work best and adapt how it learns.

Two principles anchor everything else. **Nodes can forget; the system remembers:** models and agents are replaceable contributors, and the Fabric owns memory. And **the database is not the intelligence:** the goal is to compress many experiences into a small amount of useful, challengeable operational knowledge, not to accumulate an ever-growing store of lessons.

### 2. Core distinctions

Four kinds of record must stay distinct, because each plays a different role and has a different lifecycle.

| Layer | What it is | Mutability | Normally delivered to workers? |
|---|---|---|---|
| Evidence | What happened: artifacts, outputs, outcomes, incidents | Immutable | No |
| Finding (lesson) | What was inferred from one or more pieces of evidence | Immutable once recorded; linked to its evidence | No |
| Procedure | Consolidated, reusable guidance for a class of work | Versioned; each version immutable | Yes, when ACTIVE and applicable |
| Application | What happened when a procedure was used | Immutable; becomes new evidence about that version | No |

Six states must never be collapsed into one another. Each is a separate claim that needs its own evidence:

**recorded → retrieved → delivered → applied → behaviour changed → outcome improved**

A procedure that was delivered has not necessarily been applied. A procedure that was applied has not necessarily changed behaviour. A behaviour change is not an outcome improvement unless a comparison shows it.

### 3. The first-order loop

The minimum continuous loop has nine stages. Every piece of real work passes through all of them; none is optional.

1. **Intake.** A real task is recorded, with the tags its creator would naturally use.
2. **Retrieve** the ACTIVE procedures that apply to it.
3. **Deliver** them into the worker's actual context, persisting exactly what was delivered.
4. **Work.**
5. **Record** the artifact evidence and the outcome.
6. **Close out.** For each procedure step, record applied or not applied, judged from artifacts. Then record findings: what failed, what surprised, what cost more than expected.
7. **Consolidate.** Propose a new procedure, a new version, a challenge or a retirement, backed by findings.
8. **Activate.** The owner approves (for now; see Section 4).
9. **Next task.**

This corresponds closely to the case-based reasoning cycle (retrieve, reuse, revise, retain), with the addition of explicit activation and artifact-judged application.

### 4. Procedures

A procedure is a Fabric-owned, versioned record. It should never live only in orchestrator code or a node's prompt: if it does, discovering or changing a procedure requires a code deploy, or happens invisibly.

Each procedure version contains:

| Element | Purpose |
|---|---|
| Ordered steps | What to do |
| Required artifact per step | What each step must produce, so application can be judged from outputs rather than from the worker's account |
| Refusal conditions | When the procedure requires the worker to refuse a claim or stop |
| Scope statement | What class of work it applies to, and under what conditions it does not apply |
| Evidence-strength label | How many incidents support it and of what kind (for example "3 incidents, uncontrolled, single project"). A factual label, not a score |
| Provenance links | The findings and evidence it was derived from, including any challenging evidence |
| Version and predecessor | Lineage, so variants and descendants can be compared |

Specific traps that don't generalise into procedures (for example, a library's surprising transaction behaviour) belong inside a procedure, as checks within the step they affect, rather than as free-floating lessons.

**Lifecycle.** A procedure moves through PROPOSED → ACTIVE → RETIRED, with challenges recorded as evidence against a specific version. Any agent may freely propose, revise or challenge. Promotion to ACTIVE requires recorded owner authority, referencing the actual approval rather than just a name. This separation of proposal from authority can loosen once the system has a record of proposing good procedures.

Weak knowledge is delivered as weak. A procedure resting on one observation should reach a worker labelled as a hypothesis, not as a rule. Promotion to a default requires replication or a controlled comparison.

### 5. Retrieval and delivery

**Normal target.** Workers receive current applicable ACTIVE procedures, not historical lessons or raw evidence. Historical material enters retrieval in only three situations: when no ACTIVE procedure applies but past incidents match the task (delivered as a short warning); during consolidation or challenge work on a specific procedure; and after a failure that matches a known incident.

**Working-set budget.** Delivered context should stay small and bounded. If it grows past an agreed budget, compression is failing and that is a stop condition.

**Indexing by applicability.** Procedures should be retrievable by the vocabulary tasks are naturally described in, not only by the vocabulary of what the procedure produces. The first real retrieval failure came from exactly this mismatch: procedures indexed by artifact type, tasks described by domain. The minimum fix is to derive each procedure version's applicability terms mechanically from the task tags of the incidents in its provenance, so the index grows from evidence rather than from anyone's knowledge of how procedures were tagged. While only a handful of procedures are ACTIVE, delivering all their scope statements is a cheap stopgap; every case where a worker judges a procedure applicable but tag retrieval missed it should be recorded as retrieval evidence.

**Delivery is verifiable.** The delivered text must equal the stored version byte for byte, and the actual working prompt must be persisted. Everything that influenced a piece of work must be in Fabric records, with no hidden context in a node, so another node could reproduce it.

### 6. Evidence integrity and Goodhart protection

The largest risk in a self-developing learning system is self-confirming learning: the agent that does the work also writes the lessons and grades their effect, so records multiply and every procedure reads as supported while evidence quality quietly erodes.

Separate the roles:

| Role | Rule |
|---|---|
| Objective setting | Human or human-approved. The system may propose changes, never enact them. |
| Execution | Nodes act only within their task. |
| Verification | Specification fixed before the work. The executing node's claims count only as labelled evidence. |
| Adaptation | Cannot edit verifiers, metrics or held-out checks. |
| Held-out evaluation | Not used for tuning and not visible to the learning loop. |

Rules that follow:

- A worker's narrative is never evidence of its own application or success. Only artifacts are: files, captured outputs, database state, execution traces, each identified by path and hash.
- Outcome and pass fields are derived mechanically from underlying evidence, never supplied by the producer.
- Expected values come from an authoritative or independently established source, never from the actual result being checked.
- Nodes report which delivered procedures they used or ignored, so a bad procedure can be distinguished from an ignored one.
- Independent review samples the machine's own records at capability boundaries, rather than reviewing every iteration.

### 7. The second-order loop (learning to learn)

Evidence about how the system learns must be captured from the start, because it cannot be reconstructed later. For every learning event, record:

| Field | Content |
|---|---|
| Learning need | The triggering evidence |
| Method and performer | How the learning was done (single-incident lesson, multi-incident consolidation, reviewer finding, ...) and by which node or model |
| Input evidence | References to what the learning drew on |
| Resulting change | Knowledge version created, modified or retired |
| Cost | Time and tokens spent on the learning itself |
| Subsequent applications | Tasks where the resulting knowledge was delivered or applied |
| Effectiveness status | Supported, challenged or unresolved, with evidence references. No score |

Three architectural properties keep the route to learning-to-learn open:

1. **Procedure-agnostic effectiveness accounting.** Cost, evidence change, decision effect and time are recorded the same way whatever procedure produced them, so a brand-new method can be compared with old ones.
2. **Frozen measurement.** The definitions used to measure learning effectiveness change only through governance, independently of the procedures they evaluate. Otherwise the system can improve its effectiveness measure by changing what the measure counts.
3. **Open vocabularies.** Action types, step types and applicability terms are not fixed lists, so genuinely new methods can be represented.

Double-loop learning (Argyris and Schön) is the organisational-theory origin of this layer: changing the assumptions and rules behind how learning is done, not only the actions it produces.

### 8. Claims of improvement

A claim that learning changed behaviour or improved outcomes needs a comparison designed to show it:

- **Concurrent baseline.** Interleave baseline and learning-condition runs in the same period; environments drift, and a comparison with an earlier period shows drift as a learning effect.
- **Competent baseline.** The baseline carries the best reasonable static guidance available at the start. Beating an unguided baseline proves little.
- **Counterfactual control.** Deliver an unrelated but non-empty guidance item as a control, to show that the guidance's content, not its presence, caused the change.
- **Replicates.** LLM output is stochastic; one run is an anecdote.
- **Pre-declared metrics, run count and time limit.**
- **Cost recorded alongside outcome**, since the learning condition consumes more.
- **Trend, not just level.** "Progressively better" requires the gap to hold or widen as learning accumulates.
- **Design-class labelling.** Every result carries whether it came from a controlled comparison, an observational before-and-after, or a single uncontrolled case.

### 9. Compression and growth

The target shape is: many experiences → fewer findings → fewer ACTIVE procedures → a small worker working set.

Compress what is delivered, not what is kept. Evidence is cheap to store and is what allows a procedure to be challenged or rebuilt later; bulky raw artifacts can be archived by hash rather than deleted. The real risk in consolidation is losing conditions and dissent: a procedure that holds in one context and fails in another, or incidents that contradict it. Procedures must carry their scope, and links to challenging evidence must survive every consolidation.

### 10. Invariants and stop conditions

**Invariants** (losing any of these makes the learning evidence misleading, unsafe or architecturally invalid):

1. A worker's narrative is never evidence of its own application or success.
2. The six states from recorded to outcome improved are never collapsed; improvement claims need a comparison.
3. Governing knowledge becomes ACTIVE only through recorded owner authority; versions are immutable with provenance.
4. Everything that influenced work is in Fabric records, reproducible by another node.
5. The loop never touches production or the Fabric's own structure without the owner.

**Stop and require owner or independent review when:**

- The loop proposes changing governing knowledge, or the learning method itself, without owner activation.
- Any action would touch production or the Fabric's schema.
- A record contradicts its artifacts, or a claim has no artifact behind it.
- A failure recurs after an ACTIVE procedure addressing it was applied.
- Findings accumulate without consolidation, or delivered context exceeds its budget.

### 11. External patterns worth borrowing from

| Pattern | Relevance |
|---|---|
| Case-based reasoning (Aamodt and Plaza) | Retrieve, reuse, revise, retain: almost exactly the first-order loop, with decades of work on case indexing and retrieval directly relevant to the vocabulary-mismatch problem |
| Knowledge-Centered Service (KCS) | Captures knowledge in the flow of work, evolves articles through defined states, retires them; closely mirrors the procedure lifecycle |
| Double-loop learning (Argyris and Schön) | The theoretical basis for the second-order loop |
 After-action reviews and blameless postmortems | Matue practice for the close-out stage: structured, non-punitive capture of what happened and why |
| ExpeL and related LLM-agent research | Agents that extract insights from task histories and add, edit or retire them; useful mainly for seeing where such systems failed |