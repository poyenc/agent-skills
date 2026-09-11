# Human-first design quality

Human maintainers are the primary audience. A change must be understandable without reconstructing agent history or development procedure.

Cognitive load is the harm this dimension measures. Every check below asks whether the change forces a maintainer to hold more in working memory than the problem requires — through unnecessary indirection, deep call chains, inconsistent or opaque names, or prose that resists skimming.

## Design and maintainability

- Prefer the smallest design that fully satisfies current requirements.
- Reuse or deepen an existing mechanism instead of adding a parallel convention.
- Give each unit one clear responsibility and one owner for each invariant.
- Require an abstraction to enforce a real boundary or invariant, serve repeated use, or materially improve testing and comprehension.
- When one function expresses one responsibility clearly, do not split it into pass-through layers; judge indirection by its cognitive cost — the call-depth and nesting a reader must trace to follow one behavior — not by unit count, and do not assert a class or function-count threshold.
- Reject speculative options, unused configuration, duplicate ownership, and APIs without current consumers.
- Check cohesion, dependency direction, coupling, hidden state, and responsibility boundaries.
- Check whether demonstrated likely changes remain localized. Do not demand flexibility for imagined futures.
- Compare the new design with nearby established mechanisms before proposing another.

## Readability

- Names must describe domain behavior, ownership, units, and constraints.
- A name is the primary abstraction: a good name conveys a unit's contract so a reader grasps intent without reading its body. Reject names so short or abbreviated that a reader must decode them, and names inconsistent with established concepts in the change or codebase — the same concept under different names, or one name spanning distinct concepts. Report a naming defect only with a concrete misread or decode cost, not a synonym preference.
- Present the main path before secondary details.
- Keep control and data flow traceable without unnecessary indirection.
- Make state transitions and side effects explicit.
- Use comments only for non-obvious reasons, invariants, constraints, or workarounds.
- Report readability only when the exact structure can cause misunderstanding, misuse, review burden, or unsafe maintenance.

## Human reviewability of a proposed submission

- Apply this section only when the compared input is one proposed submission or acceptance unit. Do not apply it to historical audits, release-to-release comparisons, or folders that intentionally aggregate independent changes.
- Require one self-contained purpose, or a set of changes that must remain atomic to preserve correctness.
- Identify independently useful changes that can be reviewed and submitted separately without breaking the repository.
- Treat size as a signal, never proof. Do not apply universal line or file limits.
- Report reviewability as a defect only when logical separability is demonstrated and the combined change forces reviewers to hold unrelated designs or obscures causal verification.
- Do not demand separation when generated output, an atomic API migration, or another demonstrated invariant requires the files to change together.

## Documentation usability

- Identify the intended reader and the task or contract the document supports.
- Put purpose, prerequisites, and durable behavior before secondary detail.
- Organize sections so readers can find one concern without reconstructing the implementation history.
- Keep prose plain and skimmable: descriptive headings and short paragraphs so a reader can scan rather than read linearly.
- Use consistent terminology, direct language, and examples tied to maintained behavior.
- Verify links and references against the target contents.
- Report documentation quality only with a concrete reader failure: missing prerequisite, ambiguous instruction, hidden contract, broken navigation, contradictory terminology, or an identified structure that materially obstructs a stated reader task.

## Human-first artifact test

Reject observable residue that burdens maintainers:

- Prompt text, agent coordination, task narration, or gate bookkeeping
- Repeated summaries and comments that restate code
- Generic scaffolding, unused hooks, placeholder abstractions, and pass-through helpers
- Tests or documentation organized around implementation phases instead of maintained behavior
- Large context dumps that make maintainers reconstruct the actual contract
- Code optimized for agent navigation at the expense of human comprehension

Never label a change as "AI slop" from tone or style alone. Name the concrete defect: readability cost, duplicate mechanism, unnecessary scope, weak test oracle, misleading documentation, or publication leakage.

## Avoid split-hair reviews

Do not report:

- A different design that is merely equally valid
- Naming or formatting already accepted by project style
- A local simplification with no concrete maintenance effect
- A hypothetical extension unsupported by current requirements or consumers
- Metric-only objections based on line count, complexity, or coverage
- Pre-existing unrelated debt

The review standard is improved code health, not the reviewer's ideal rewrite.
