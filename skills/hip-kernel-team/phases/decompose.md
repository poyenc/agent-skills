# Decompose Multi-Member Tasks

When a task requires multiple team roles, decompose it into a pipeline
of chained tasks. Read this file before creating multi-member task
batches.

## How To Use

1. Identify which pipeline pattern fits the goal
2. Create one task per stage using TaskCreate
3. Chain stages with `addBlockedBy`
4. Use the naming convention: `"<goal>: <stage>"`
5. Assign each task to the role specified by the template
6. After the final stage completes, evaluate via the Decision Framework

Templates are rigid by default. To skip a stage, log a one-line
justification in status.md (see Escape Hatch).

---

## Pipeline Templates

Each template defines **one iteration**. The lead manages the loop —
re-enter at any stage for the next iteration, stop when done. Iteration
budget from the lead role applies.

### Optimize

**Pattern:** research → implement → QA verify → benchmark
**Use when:** Chasing a perf gap with an unknown root cause.

```
Stage 1: Research    → researcher  → output: /tmp/<team>/researcher-<topic>/<topic>.md
Stage 2: Implement   → implementer → blockedBy: stage 1 → code changes + structured output
Stage 2a: QA verify  → lead spawns QA subagent (not a task) → PASS/FAIL
Stage 3: Benchmark   → profiler    → blockedBy: stage 2 (QA pass) → benchmark + diagnosis if regression
```

- **QA rule:** Lead spawns QA subagent between stage 2 and 3. Not a
  task — an inline subagent call. Benchmark is not assigned until QA
  passes.
- **Diagnosis rule:** If profiler detects regression, investigation is
  inline within the benchmark task (rocprof, ATT, stall analysis).
- **Revert scope:** Stage 2 code changes only. Research is always kept.
- **Naming:** `"<goal>: research"`, `"<goal>: implement"`,
  `"<goal>: benchmark"`.

### Experiment

**Pattern:** implement → QA verify → benchmark
**Use when:** The change is known, just needs to be tried and measured.

```
Stage 1: Implement   → implementer → code changes + structured output
Stage 1a: QA verify  → lead spawns QA subagent (not a task) → PASS/FAIL
Stage 2: Benchmark   → profiler    → blockedBy: stage 1 (QA pass) → benchmark + diagnosis if regression
```

- **Revert scope:** Stage 1 code changes only.
- **Naming:** `"<goal>: implement"`, `"<goal>: benchmark"`.

### Investigate

**Pattern:** parallel research → lead synthesizes
**Use when:** Problem space unclear, multiple angles needed.

```
Stage 1a..N: Research → any role → parallel (no blockedBy between them)
Stage 2:     Synthesize → lead   → blockedBy: all stage 1 → status.md update
```

- **Revert scope:** None — no code changes.
- **Naming:** `"<goal>: investigate <angle>"` per stage 1 task. No
  stage 2 task — lead synthesizes directly after all stage 1 tasks
  complete, then evaluates via the Decision Framework.

### Hotfix

**Pattern:** implement → QA verify → benchmark (optional)
**Use when:** Correctness fix where perf is secondary.

```
Stage 1: Implement   → implementer → code changes + structured output
Stage 1a: QA verify  → lead spawns QA subagent (not a task) → PASS/FAIL
Stage 2: Benchmark   → profiler    → blockedBy: stage 1 (QA pass) → OPTIONAL
```

- **QA rule:** QA performs clean rebuild + full test suite. Especially
  important for hotfixes since correctness is the primary concern.
- **Revert scope:** Stage 1 code changes only.
- **Stage 2 rule:** Include when the fix touches kernel code (pipeline
  headers, policy headers, kernel wrappers). Skip with justification
  for non-kernel fixes (test infra, build scripts, dispatch logic).
- **Naming:** `"<goal>: implement"`, `"<goal>: benchmark"`.

---

## Decision Framework

After the final stage of each iteration, evaluate:

| Result | Action | Re-entry |
|--------|--------|----------|
| Goal met | Commit changes, mark done | STOP |
| Partial improvement | Keep gains, decide next step | Any stage (new iteration) |
| Regression | Revert code changes | Research or STOP |
| Spills / test failure | Revert code changes | Implement or STOP |
| Budget exhausted | Document as exhausted | STOP |

### Re-entry

- Create a **new task batch** using the same template, referencing
  prior iteration results in the task descriptions.
- Naming: `"<goal> (iter N): <stage>"` for iterations beyond the first.
- Select re-entry point based on what the evaluation revealed:
  - Wrong approach → re-enter at Research
  - Right approach, wrong implementation → re-enter at Implement
  - Tests failed → re-enter at Implement (fix the code)
- Re-entry point selection is the lead's most important judgment call.

### Stop Criteria

Stop iterating when any of:
1. Goal met (evaluation criteria from config)
2. Iteration budget exhausted (risk level from lead role)
3. Approach added to exhausted list in status.md
4. User explicitly says to stop

---

## Escape Hatch

Skip any stage with a one-line justification in status.md. The template
is rigid by default — deviations must be logged.

Examples:
- `"Skipped research: findings from Task #12 (2026-04-25) still apply."`
- `"Skipped benchmark: non-kernel fix (test infrastructure only)."`
- `"Merged implement+test: single-member hotfix, no handoff needed."`

---

## Handoff Protocol

Handoff between stages uses output file paths:

1. Upstream member saves results to `/tmp/<team>/<role>/`
2. Upstream member reports completion to lead with the file path
3. Lead references the file path in the downstream task description
4. Downstream member reads the file to get context

No structured handoff documents. No direct peer messages for handoff —
all routing goes through lead via task assignments.

**QA subagent handoff:** QA is not part of the handoff chain. The Lead
spawns QA as an inline subagent between stages — it reads the
implementer's structured output and the task spec directly. No file
handoff needed for QA.

---

## Pipeline Proposals

Any idle member can propose a new pipeline direction:

1. **Propose:** Message lead with:
   - Goal (what to achieve)
   - Suggested pattern (Optimize / Experiment / Investigate / Hotfix)
   - Rationale (why this direction, what evidence supports it)
2. **Lead evaluates** against:
   - Current task list (avoid duplication)
   - Iteration budget (can we afford this?)
   - Exhausted approaches list (don't retry dead ends)
3. **Lead decides:**
   - **Accept** → Decompose using the template, create tasks
   - **Defer** → Note in status.md for later
   - **Reject** → Document reasoning in status.md

---

## Workload Balance

Workload differences are inherent to roles:
- Implementer: every pipeline (always needed for code changes)
- Profiler: 3 of 4 pipelines (always needed for measurement)
- Researcher: 1-2 pipelines (investigation-heavy, then idle)

Mitigation: Only spawn roles that have tasks in the current pipeline.
Idle members can propose new pipeline directions.
