# Tests, delivery, and artifacts

## Discover delivery procedure

Read the base input before the target. Search hidden files when supported.

After applying `standards.md`, inspect mechanically enforced repository configuration; maintainer-facing contribution instructions; live interfaces, tests, and consumers; and repeated analogous merged changes. Historical practice corroborates repository intent but does not create policy.

Do not assume a project uses handoffs, plans, a specific continuous-integration service, or any named development process.

Do not use a commit message alone to prove that an alternative implementation must become a supported product path. Require an explicit request, maintained documentation, public-interface change, or production consumer; otherwise place reachability ambiguity under investigation needed.

Extract applicable commands and prerequisites for the report, but do not execute them. Check whether the target follows the established delivery path or intentionally replaces it with a portable, documented, consumed mechanism.

## Test quality

- Map changed behavior and failure modes to relevant tests.
- Check that assertions observe external behavior or a stable contract.
- Require independent expected values; reject tests that reproduce implementation logic.
- Check boundaries, invalid inputs, regressions, and meaningful integration seams.
- Reject one-shot gate tests, existence-only tests, unexplained snapshots, and hashes of implementation output unless exact output is the product contract.
- Check determinism, portability, isolation, and maintenance cost.
- Do not require arbitrary coverage percentages or one new test per changed line.
- State author-run verification without claiming it ran.

## Artifact disposition

Keep an added artifact only when evidence shows that it:

- Supports a stable product or delivery contract
- Works from a clean clone with declared prerequisites
- Has a real consumer in the normal product, build, test, documentation, or release path
- Adds unique value instead of wrapping an established command or mechanism
- Has a stable oracle when it verifies behavior
- Has clear ownership and ongoing maintenance value
- Uses product language rather than implementation-phase language

Potential one-shot residue includes freeze or extraction helpers, transitional snapshots, self-comparison tests, wrappers created only for an agent procedure, tests of helper existence, task or gate terminology, dated process documents, and generated evidence. Inspect semantics before deciding; a regression fixture may remain when it protects a stable contract with an independent oracle.

A test is a real consumer of test-support code but does not establish production reachability. Test-only code belongs under `tests/` or an established test-support location; test usage alone does not justify placing it on a production or maintained-tools surface.

## Publication leakage

Inspect all published surfaces available to the comparison:

- Filenames and contents
- Source, tests, scripts, configuration, and documentation
- Generated artifacts and provenance
- Commit subjects and bodies
- Pull-request title and body when supplied

Treat personal paths, usernames beyond ordinary authorship, machine details, agent names, prompts, task counts, plan or specification artifacts, gate names, handoffs, scratch paths, raw logs, temporary evidence, and committed secrets or credentials as leakage candidates. Block only when the item is local development-session or process residue without a durable repository consumer or maintenance purpose, and state the resulting publication or maintenance harm. Do not flag legitimate product concepts or maintained design documentation merely because they mention agents, plans, or specifications.

Use repository-relative paths in reports. Do not copy leaked values into the report; identify their location and category with necessary redaction.

## Scope accounting

Classify every changed artifact as outcome-related, delivery-required, a finding candidate, or examined and non-defective. Require an explicit user requirement, an enforced repository requirement, or evidence that the artifact is unavoidable for the requested outcome. An assistant or reviewer's proposed integration is not a requirement unless the user explicitly adopts it.

Before accepting a new dependency on another component, ask whether the requested outcome works without that dependency. If yes, exclude the integration from the proposed scope. Do not expand into adjacent components merely to make an optional integration complete.

Evaluate unrelated cleanup, formatting sweeps, duplicate infrastructure, and development residue under the normal finding gate; do not promote harmless scope into a defect. Do not turn one historical change into policy.
