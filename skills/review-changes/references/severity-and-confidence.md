# Severity and confidence

Classify severity from demonstrated consequence. Classify confidence from evidence strength. Do not use confidence to lower severity.

## Severity

Use the normalized severity below for readiness. When a repository declares its own taxonomy, report both its native label and the normalized severity; explain the mapping from demonstrated impact.

| Severity | Required consequence |
|---|---|
| Critical | Credibly reachable serious physical harm, broad unrecoverable loss or corruption of important data, or loss of a core service for most users without a practical workaround. |
| High | A primary supported workflow is materially wrong or unusable; a common path crashes; important data is corrupted or disclosed with bounded or recoverable impact; or an established public contract breaks without a practical workaround. |
| Medium | A secondary workflow is wrong; reliability materially degrades under a plausible limited condition; impact is limited to a subset of users or components; recovery exists; or design damage substantially obstructs safe future changes. |
| Low | A real localized defect causes bounded maintenance cost, unnecessary duplication, misleading affected documentation, confusing code with identifiable human cost, or unintended non-sensitive process or environment disclosure. |
| Advisory | Personal style preference, optional simplification, harmless plan mismatch, or speculation without a demonstrated consequence. This is not a defect. |

Every confirmed Low-or-higher defect introduced, worsened, or exposed by the change blocks readiness. Advisory observations never block.

For each severity, state the trigger, affected behavior or asset, scope, duration and recovery, workaround, and evidence. Do not infer severity from code size, change size, a tool label, or reviewer discomfort.

## Confidence

Use the lowest band supported by the evidence:

| Score | Evidence |
|---|---|
| 95-100% | Reproduced from static artifacts, mechanically proven, or established by an unambiguous control-flow, data-flow, type, or contract contradiction. |
| 80-94% | Direct source trace supports the finding, with every remaining assumption explicit and credible. |
| 60-79% | Plausible concern missing decisive source, environment, or domain evidence. Investigation needed; never blocking. |
| Below 60% | Omit. The concern is too speculative to spend maintainer attention. |

The percentages are this skill's evidence policy, not an industry standard.

## Finding verification

Before admission, try to disprove the candidate:

1. Re-read the exact target code and relevant base code.
2. Trace the real caller, consumer, or reference path.
3. Search for validation, normalization, fallback, or ownership elsewhere.
4. Check whether the triggering condition is supported and reachable.
5. Check whether repository rules or established contracts permit the behavior.
6. State unresolved assumptions and lower confidence accordingly.

## Fix verification

Describe a concrete verification procedure the author can perform after fixing the issue. It must target the stated consequence, fail on the reviewed change when feasible, pass after the fix, and include regression coverage appropriate to the contract. Do not claim the procedure ran.
