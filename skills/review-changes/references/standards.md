# Standards and authority

Use standards as review evidence, not badges. Never claim formal compliance from a change review.

## Core references

- [Google Engineering Practices: The Standard of Code Review](https://google.github.io/eng-practices/review/reviewer/standard.html): approve changes that improve overall code health. Prefer technical facts over personal opinion. Do not demand perfection when a change clearly improves the system.
- [Google Engineering Practices: What to Look For](https://google.github.io/eng-practices/review/reviewer/looking-for.html): review design, functionality, complexity, tests, naming, comments, consistency, documentation, and every human-written changed line in system context.
- [Google Engineering Practices: Small Changes](https://google.github.io/eng-practices/review/developer/small-cls.html): prefer one self-contained change because smaller changes are reviewed more thoroughly and are easier to reason about. It explicitly rejects a universal size limit.
- [Google Developer Documentation Style Guide](https://developers.google.com/style): useful evidence for clear, concise, audience-focused documentation. Treat its principles as this skill's heuristics unless the repository adopts the guide; do not cite it as a binding external requirement otherwise.
- [ISO/IEC 25010:2023](https://www.iso.org/standard/78176.html): use applicable product-quality dimensions as prompts. This skill focuses on functional suitability, performance efficiency, compatibility, reliability, maintainability, and flexibility. The normative standard is licensed; do not claim ISO conformity.
- [ISO/IEC/IEEE 29148:2018](https://www.iso.org/standard/72089.html): use its requirements-engineering concepts to distinguish stakeholder needs, requirements, design constraints, and verification evidence. Assess whether requirements are necessary, unambiguous, feasible, verifiable, singular, and traceable. The normative standard is licensed; do not claim conformity.
- [IEEE 1044-2009](https://standards.ieee.org/ieee/1044/4402/): keep anomaly impact or severity separate from corrective-action priority. This skill uses that distinction but does not claim IEEE conformity.

## Application rules

Use this authority order:

1. Explicit user requirements
2. Observable behavior and repository contracts
3. Applicable authoritative engineering standards
4. Repository conventions
5. Plans and issues as background intent
6. Commit messages, comments, optional handoffs, and saved results as claims requiring verification

Fresh source evidence beats stored prose. Enforced behavior beats descriptive prose. Apply repository-defined standards before general conventions when they do not conflict with explicit user requirements or observed behavior.

- Cite an external rule only when its scope and preconditions match the finding.
- Do not turn guidance into universal numeric limits for coverage, complexity, duplication, function length, or change size.
- Do not use a standard to disguise personal preference.
- Do not perform vulnerability or cyberattack review. Publication leakage remains repository hygiene because it changes what the repository exposes to humans.

## Requirements quality

- Separate the requested outcome from an implementation proposal or process preference.
- Require each inferred requirement to be necessary, singular, feasible, and statically verifiable.
- Trace every requirement to affected artifacts and evidence; trace every changed artifact back to an accepted requirement or unavoidable delivery obligation.
- Surface ambiguous or conflicting requirements instead of silently choosing an interpretation.
- Never promote a reviewer suggestion into scope without explicit user acceptance.
