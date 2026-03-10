---
name: ck-fmha-codegen-guide
description: >
  Generate comprehensive FMHA kernel selection guides by dynamically analyzing
  CK codegen source code. Produces filename structure documentation, field
  references with dispatch semantics, recommended minimal kernel sets, and
  ready-to-use filter commands for generate.py. Use this skill whenever the
  user asks about: kernel selection for any FMHA API, minimal kernel sets,
  codegen filters, what fields are in a kernel filename, how to reduce kernel
  count, understanding fwd/bwd/splitkv/appendkv/batch_prefill/pagedkv_prefill
  kernel variants, "which kernels do I need", "how do I filter kernels",
  "generate a kernel guide", "explain the filename structure", or any question
  about reducing or selecting FMHA codegen output. Also trigger when the user
  mentions "kernel selection guide", "minimal set", "filter pattern", or wants
  to understand the codegen options for a specific FMHA direction/API.
---

# CK FMHA Kernel Selection Guide Generator

Generate a comprehensive, up-to-date kernel selection guide for any CK FMHA
API by reading the codegen source code directly. The guide is derived from
the code itself — never from cached knowledge — because the codegen evolves
frequently.

## When to use

- User asks for a kernel selection guide for an FMHA API
- User wants to know what the minimal kernel set is
- User wants filter commands for `generate.py`
- User asks about filename fields, padding, or feature axes

## Inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| API name | Yes | — | One of the APIs from `codegen/ops/` (e.g., `fwd`, `bwd`, `fwd_splitkv`) |
| Target arch | No | `gfx9,gfx950` | GPU architecture(s) to consider |
| CK root | No | auto-detect | Path to the CK repo root |

If the user doesn't specify an API, list the available APIs discovered in
Step 1 and ask which one to analyze.

## Workflow

### Step 0: Locate the CK codegen directory

Find the CK repo root by searching upward from the current working directory
for the `.ck-project-root` marker file. If not found, search for
`example/ck_tile/01_fmha/codegen/ops/` relative to likely root directories.
Also check if you're inside a submodule — the CK root may be a subdirectory
of a parent repo. Set:

```
CODEGEN_DIR = <ck-root>/example/ck_tile/01_fmha/codegen
OPS_DIR     = <CODEGEN_DIR>/ops
GENERATE_PY = <ck-root>/example/ck_tile/01_fmha/generate.py
```

Also note these supporting files for later steps:
- `CODEGEN_DIR/cpp_symbol_map.py` — C++ symbol maps for feature values
- `CODEGEN_DIR/arch.py` — architecture trait definitions and factory dispatch
- `CODEGEN_DIR/utils.py` — shared utilities (file writing, validation)

### Step 1: Discover available APIs

List all `.py` files in `OPS_DIR` (excluding `__init__.py`). Each file
`fmha_<api>.py` corresponds to API name `<api>`. Present the list to the
user if they haven't specified which API to analyze.

Also read `generate.py` to confirm how module names map to API handler
keys — the script strips a prefix from module names to create the keys.
Verify the mapping matches what you'd expect from the filenames.

### Step 2: Read and analyze the ops module

Read the full content of `OPS_DIR/fmha_<api>.py`. Each ops file is
self-contained with dataclasses, kernel classes, factory classes, blob
generation, API dispatch, and receipt filtering — but the internal
structure varies significantly across APIs.

**Do not assume all APIs share the same class hierarchy or patterns.**
Read the actual code for the target API and adapt your analysis.

Below are the key pieces of information to extract. For each, guidance
is given on what to look for, but the exact class names, method names,
and code patterns will differ between APIs.

#### 2a: Identify kernel sub-types

Determine how many distinct kernel types the API produces. Look for
`@dataclass` classes that have a `filename` property — these are kernel
classes. (Other dataclasses like tile sizes, pipelines, and API traits
may have a `name` property but not `filename`.)

Record:
- How many kernel classes exist (1 = single-kernel API, 2+ = multi-kernel)
- Each kernel class name
- Whether the kernel dataclass is `frozen=True` (affects deduplication)

#### 2b: Extract tile size definitions

Find dataclass(es) that define the tile geometry. They typically have
names containing `TileSize` but verify by looking at the fields — tile
classes contain dimensional parameters (block sizes, occupancy, etc.).

Key things to record:
- The fields and their comments (they document what each dimension means)
- The `name` property — shows how tile fields are encoded in the
  filename (e.g., `b{bm0}x{bn0}x...`)
- Fields with default values — may represent optional specializations
- Whether the tile class is defined locally or imported from another
  ops module

Tile sizes are **not independently filterable** — they come as complete
definitions from factory classes. But fields embedded in the tile name
(like `_o{occupancy}` or `_maxq{val}`) can appear in filter patterns.

#### 2c: Understand feature fields and their possible values

Feature fields may live directly on the kernel dataclass, on a separate
pipeline/trait dataclass that the kernel references, or on composed
context objects. Trace the kernel class fields to find all features
that affect the generated filename.

Cross-reference with the imports at the top of the file to find which
maps from `cpp_symbol_map.py` are used. The map keys are the valid
values for each field. Common maps include those for dtype, bias, mask,
dropout, mode, layout, and pipeline — but which ones are used depends
on the API.

Read `CODEGEN_DIR/cpp_symbol_map.py` for full map definitions when the
imports alone aren't sufficient.

#### 2d: Extract the kernel name construction

Read the `name` property of **each** kernel dataclass. This is the single
most important piece of code — it determines:

- The exact filename segment order
- How padding is encoded. Look for a `pad_name()` helper (typically a
  nested function inside the `name` property). It builds a string from
  whichever pad flags the kernel uses. Different kernel sub-types may
  use different padding dimensions and encodings (numeric like 0/8/1 vs
  boolean t/f). Read the actual code to determine which. For example,
  in `fmha_fwd.py`, `pad_name()` concatenates dimension-letter suffixes
  (`s`, `sk`, `d`, `dv`) after a `p` prefix — producing values like
  `npad`, `psddv`, `psskddv`, `pssk`, `pddv`. Other APIs may use a
  different encoding scheme.
- How boolean/enum features are encoded in the name string (e.g.,
  `n<feature>` for absent, `<feature>` or `<feature>_<variant>` for
  present)
- Any conditional segments (e.g., mask encoding may differ between
  modes). Pay special attention to the mask field — its filename
  encoding depends on the `--mask` / `mask_impl` parameter passed to
  `generate.py`. In simplified mode (`--mask=simplified`, the default),
  mask values are `s_no` and `s_mask`, which encode as `nmask` and
  `mask` in the filename. In generic mode (`--mask=generic`), mask
  values are `no`, `causal`, `generic`, which encode as `nmask`, `mc`,
  `mg`. The guide must document which mode was used and note that
  switching `--mask` produces a completely different set of mask values
  in the kernel names.

#### 2e: Identify architecture-specific factories

Find classes that produce tile sizes, pipelines, and kernel
configurations per GPU architecture. Search broadly for classes
containing `Factory` in their name — the exact naming convention varies
across APIs (e.g., `KernelComponentFactoryBase`, `KernelComponentFactory`,
or more elaborate hierarchies with `CompatibilityRuleFactory`).

Key things to determine:
- Which factory classes exist and their inheritance hierarchy
- Which tile sizes each factory provides per architecture
- Which dtypes are supported (factories may return empty lists for
  unsupported dtypes)
- Whether there is a `get_factory(target)` function that maps target
  strings to factory classes

Also check `CODEGEN_DIR/arch.py` for `get_factories_for_targets()` —
this shared function deduplicates factories across targets and sorts
them by specificity.

**Note:** Some APIs may not have arch-specific factories at all — they
may use a single factory class. Verify by checking whether the main
blob generation function accepts a `targets` parameter.

#### 2f: Understand the blob generation and filter mechanism

Find the main function(s) that enumerate kernel instances. Look for
functions whose names contain `blobs` (e.g., `get_fwd_blobs`,
`get_bwd_blobs`). Also check `write_blobs()` and `list_blobs()` — in
multi-kernel APIs, these top-level entry points may orchestrate multiple
internal blob functions.

Key things to extract:

**Filter parsing** — determine how the filter string is processed:
- Single-kernel APIs typically apply `fnmatch` directly to each kernel name
- Multi-kernel APIs may split the filter by `@` to create separate
  sub-filters for each kernel type. Check how many parts the split
  produces and which sub-filter position maps to which kernel type.
  The split may happen in `write_blobs`/`list_blobs` rather than in the
  `get_*_blobs` function itself.

**Cross-product** — look for `itertools.product(...)`. This shows which
fields are combined to generate all kernel variants.

**Skip conditions** — the `continue` statements after the cross-product
are critical. They encode constraints that prune invalid combinations
(e.g., group mode padding requirements, incompatible feature pairs,
architecture-specific restrictions). Read and document each one.

**fnmatch application** — look for `fnmatch.fnmatch(...)` calls. They
show which kernel type each filter applies to.

**Dedup** — determine how duplicate kernels are eliminated. Common
patterns include `OrderedDict` keyed by the kernel object (requires
frozen dataclass) or other dedup mechanisms. The mechanism varies — read
the code to determine which is used.

**Compatibility rules** — some APIs use a compatibility rule system
where kernel-problem compatibility is checked via callable rule objects
rather than simple skip conditions. If you find classes with names
like `CompatibilityRule` or `Product`, these serve this purpose.

**Cross-module field values** — some pipelines may hardcode values
from a different symbol map than the one controlled by user parameters.
For example, a specialized pipeline might use values from the generic
mask map even when `mask_impl="simplified"` is set. Check whether any
pipeline construction bypasses the `mask_impl` (or equivalent) parameter
and hardcodes specific map values directly. If so, document this in the
guide's field reference — these values will appear in the kernel names
regardless of the user's mask mode setting.

#### 2g: Understand receipt filtering

In the blob generation function(s), search for `if receipt ==` blocks
or similar receipt-based filtering. These filter the kernel set for
specific integration targets. Document the receipt values and what
constraints each applies (dtype, mode, bias, dropout, etc.).

### Step 2.5: Cross-check your structural findings

Before proceeding, verify these key characteristics of the API you're
analyzing. They affect how you interpret later steps:

| Question | Impact |
|---|---|
| How many kernel classes did you find? | 1 = single filter, 2+ = may need `@`-separated sub-filters |
| Does the main blob function accept `targets`? | No = no arch-specific factories to document |
| Is the kernel dataclass `frozen=True`? | Affects dedup mechanism description |
| Does the ApiPool have a `render()` method or an `api` property? | Determines how to analyze dispatch order |
| Does the filter get split by `@`? | Determines filter mechanism section structure |
| Are there compatibility rules or just skip conditions? | Affects how pruning logic is documented |

Adjust subsequent steps based on what you actually found. Do not force
the code into a pattern it doesn't follow.

### Step 3: Analyze runtime dispatch order

Find the `ApiPool` class (name varies) and determine how it generates
the C++ dispatch code. Look for:

- A method or property that produces the `if / else if` chain (may be
  called `api`, `render()`, or something else — read the class)
- How traits are registered and in what order
- Any explicit sort calls that reorder the dispatch chain
- Padding variant ordering (more restrictive variants typically come
  first so the least-padded kernel that fits is chosen at runtime)

### Step 4: Validate filter patterns (if Bash is available)

If you have Bash access, verify every filter pattern before including it
in the guide. A pattern that looks correct can silently match more or
fewer kernels than intended.

#### 4a: Get the unfiltered baseline

```bash
cd <ck-root>/example/ck_tile/01_fmha
python3 generate.py --api=<api> --targets=<targets> -l /tmp/<api>_all.txt -r 0
wc -l /tmp/<api>_all.txt
```

The `-r 0` flag sets the receipt to `0`. Note that `-r 0` is technically
still a receipt filter (it passes through `get_product(0)` which returns
a `Product` rule), but in practice it produces the largest kernel set
because its product rule is the least restrictive. It is NOT "no
filtering" — some combinations may still be excluded by the product
rule for receipt 0. However, it serves as the practical baseline for
counting and comparison. Without `-r`, the default receipt is also `0`,
but being explicit avoids ambiguity.

Note: if the API doesn't support `--targets` (check Step 2.5), omit it.

#### 4b: Break down the baseline by field values

For each feature field you plan to filter on, extract all unique values
from the unfiltered list. This tells you the full universe of values:

```bash
# Per sub-kernel type (for multi-kernel APIs)
grep '<sub-kernel-prefix>' /tmp/<api>_all.txt | wc -l

# Per field — adapt the regex to match the field's encoding in filenames
# Example for pad field:
grep '<sub-kernel-prefix>' /tmp/<api>_all.txt | grep -oE '<field_regex>' | sort | uniq -c
```

Use the `name` property code (Step 2d) to craft the right regex for each
field. The exact encoding varies — boolean fields use `n<feat>/<feat>`,
pad fields use dimension-letter suffixes (e.g., `npad/psddv/psskddv`),
etc.

**Caution:** When writing regex patterns for field extraction, ensure
they don't accidentally match substrings of unrelated fields. For
example, a pad-field regex like `_(npad|p[a-z]+)` will also match
`_pertensor` from the qscale field. Use field boundary anchors
(`(?=_)` lookahead or explicit next-segment matching) to avoid
cross-field contamination. Always verify regex results against the
known field positions in the kernel name.

#### 4c: Apply the filter and count

```bash
python3 generate.py --api=<api> --targets=<targets> -l /tmp/<api>_filtered.txt -r 0 \
  -f '<filter_pattern>'
wc -l /tmp/<api>_filtered.txt
```

#### 4d: Break down the filtered output by the same fields

Run the same `grep -oE ... | sort | uniq -c` commands from 4b on the
filtered list. Compare against the baseline breakdown:

- **Intended values should be present** with expected counts
- **Dropped values should be absent** — if they still appear, the
  filter pattern is too permissive
- **No unexpected side effects** — check that unrelated fields weren't
  accidentally filtered

#### 4e: Verify the API dispatch file

The API dispatch file contains the runtime `if/else if` dispatch chain.
It is generated from the same filtered kernel set and written to the
output directory. Its filename varies by API — check the ops module for
the API filename constant.

**Critical:** `generate.py` overwrites the API file on each run. If
you run `generate.py` twice with different filters into the same output
directory, the second run's API file replaces the first. The kernel
`.cpp` files from run 1 still exist on disk but the API dispatch no
longer routes to them — they become orphaned (compiled but unreachable).

To verify the API file is consistent with the kernel files:
- Generate with the filter into a temp output dir
- Check that the API file's dispatch entries reference only the kernel
  traits that correspond to generated `.cpp` files
- If the minimal set requires multiple runs, warn that only the last
  run's dispatch is active (see fnmatch limitations below)

If Bash is not available, include all verification commands in the guide
so the user can run them.

### Step 5: Generate the guide

Produce a structured markdown document with the sections below. Derive
all content from the code analysis (Steps 2-3) and validated filter
data (Step 4) — do not use hardcoded field names or values from this
skill document.

#### Section 1: Kernel Sub-types

List each kernel sub-type, its class name, and its purpose. For
multi-kernel APIs, explain how they work together.

#### Section 2: Filename Structure

Show the full filename pattern with labeled segments for each kernel
sub-type. Derive this directly from the `name` property code.

For multi-kernel APIs, show each sub-kernel's pattern separately and
note which padding dimensions each uses (they may differ).

#### Section 3: Filter Mechanism

Document how `generate.py`'s `-f` flag is processed for this API:
- For single-kernel APIs: the filter is applied directly via fnmatch
- For multi-kernel APIs: document the `@`-separated sub-filter
  structure with labeled positions

Also note that `generate.py` splits `-f` by **comma** when multiple
APIs are requested via `-a` — each API gets its own filter segment.

#### Section 4: Field Reference

For each independently filterable field in the filename, create a table:

```markdown
### `{field_name}` — {Human-readable description}

| Value | Meaning | Dispatch condition |
|---|---|---|
| `value1` | ... | ... |
```

Include the dispatch priority (which value is tried first at runtime).
Skip tile-internal fields that are not independently filterable.

**Derive all field names and values from the code.** Different APIs
have different feature fields.

#### Section 5: Recommendation — Minimal Kernel Set

Create a "what to keep / what to drop" table based on the fields
actually present in the target API:

```markdown
| Field | Keep | Drop | Rationale |
|---|---|---|---|
```

Apply these general principles to each field discovered in Step 2c:
- **Padding fields:** Keep the no-pad variant + moderately-aligned
  variants. Drop fully-padded variants (widest alignment).
- **Optional features** (bias, dropout, rope, logits soft cap, etc.):
  Default to keeping the "disabled/no" variant. Add the enabled variant
  only if the user's workload requires it.
- **Mask variants:** Keep the no-mask + most common mask type. Drop
  less common mask types unless needed.
- **Mode-specific tuning** (e.g., short-sequence optimizations): Keep
  the general variant. Drop specialized variants unless the user's
  workload matches.
- **Deterministic/reproducibility flags:** Keep the default (usually
  non-deterministic). Add deterministic only if bitwise reproducibility
  is required.
- **Any other feature fields:** Default to the "off/no/base" variant
  unless the workload requires the feature.

#### Section 6: "What You Lose" Summary

Briefly explain the performance or coverage impact of each dropped
variant, so the user can make an informed decision.

#### Section 7: Filter Commands

Provide ready-to-use `generate.py` commands. **Critical:** account for
the fnmatch OR limitation (see below) — if the minimal set requires
multiple values for one field, show multiple generate runs.

For multi-kernel APIs, show the `@`-separated filter pattern with clear
labels for each sub-filter position.

Also show example combinations with specific dtype, hdim, or receipt.

#### Section 8: Kernel Counts

If Bash was available (Step 4), include a table of counts. Cross-check
the numbers against the Step 4b/4d field breakdowns to ensure
consistency.

```markdown
| Set | Total | kernel_a | kernel_b | ... |
|---|---|---|---|---|
| Full (no filter) | N | ... | ... | ... |
| Minimal | M | ... | ... | ... |
| **Reduction** | **X%** | ... | ... | ... |
```

---

## fnmatch limitations

Python's `fnmatch` only supports `*`, `?`, `[chars]`, and `[!chars]`.
It does **not** support:

- **OR / alternation** — no `{npad,pd8dv8}` syntax
- **Negation of substrings** — `[!x]` only excludes single characters

This means a single filter pattern **cannot select two non-overlapping
values** of the same field. For example, to keep both `npad` and `pd8dv8`
while excluding `pd1dv1` and mixed variants, you cannot write a single
fnmatch pattern — `[np]*` would match `pd1dv1` too since it starts with
`p`.

### Impact on multi-run generate

When the minimal set requires multiple `generate.py` runs with different
filters, `generate.py` produces two kinds of output:

- **Kernel `.cpp` files** accumulate safely across runs (written via
  `update_file()`, only overwrites if content changed).
- **API dispatch file** is **overwritten** on every run. Only the last
  run's dispatch chain survives — kernel files from earlier runs become
  orphaned (compile but never dispatched).

When the generated guide recommends multiple runs, it **must include a
caution** that the API file needs to be merged from all runs, and
explain why (the API file is the runtime dispatch — without merging,
only the last run's kernels are reachable).

For listing (`-l`), the output file is truncated on each run, so merge
manually:

```bash
python3 generate.py ... -l /tmp/set_a.txt -f '<filter_a>'
python3 generate.py ... -l /tmp/set_b.txt -f '<filter_b>'
sort -u /tmp/set_a.txt /tmp/set_b.txt | wc -l
```

Note: `-l` only lists filenames and does not produce an API file, so
the merge issue does not apply to listing.

---

## Important principles

1. **Always read the code.** Field names, values, class structures, and
   dispatch logic change over time. Never rely on previously memorized
   knowledge about the codegen structure — including the hints in this
   skill document.

2. **The `name` property is the filter target.** The `-f` filter matches
   against the kernel's `name` property (not `filename` — `filename`
   adds the arch suffix and `.cpp`). Construct patterns accordingly.

3. **Each API has its own internal structure.** Do not assume all APIs
   share the same class hierarchy, factory pattern, or filter mechanism.
   Read the target API's code and adapt your analysis to what you find.

4. **Dispatch order determines the fallback chain.** The runtime tries
   variants in a specific order. The minimal set only needs to cover
   variants up to the fallback the user is willing to accept.

5. **Tile sizes are not independently filterable.** They come as
   complete definitions from factory classes. Don't try to filter
   individual tile dimensions — note which configurations exist and
   what architectures they serve.

6. **Only document fields that actually exist in the target API.**
   Feature fields vary across APIs. Do not include fields from other
   APIs in the guide.

7. **Different sub-kernels may use different padding dimensions.**
   Read each kernel class's `pad_name()` to discover which pad fields
   it uses. A filter on one `@`-position only affects that sub-kernel's
   count — other sub-kernel counts stay the same.

8. **Validate filter patterns empirically.** Always verify with
   `generate.py -l` and inspect the actual filenames. A pattern that
   looks correct may match more or fewer kernels than expected due to
   fnmatch semantics (see fnmatch limitations above).

9. **`generate.py` uses comma-separated filters for multi-API runs.**
   When `-a fwd,bwd` is used with `-f`, the filter string is split by
   comma to assign one filter per API. The `@` separator (for sub-kernels
   within one API) is a separate, inner mechanism used only by APIs that
   have multiple kernel types.

---

## Hints (may be outdated — always verify against the code)

These observations were accurate as of early 2026 but may have changed.
Use them as starting points for discovery, not as authoritative facts.

- `fmha_fwd.py` is structurally more complex than other APIs. It uses a
  `ProblemContext`/`KernelContext`/`CompatibilityRule`/`Product`
  abstraction for kernel generation and compatibility checking. Its
  `FmhaFwdKernel` is not frozen. Its `FmhaFwdApiPool` uses a `render()`
  method (not an `api` property) and generates two dispatch functions
  (`fmha_fwd_v2` and `fmha_fwd_v3`), with a top-level `fmha_fwd()`
  entry point that dispatches between them. **Important:** v3 pipeline
  kernels (`qr_async_trload_v3`) ARE generated and compiled, but the
  `write_fwd_api()` function hardcodes `F_is_v3_enabled=false` in the
  API footer, making the `fmha_fwd_v3` dispatch function dead code at
  runtime. The guide should note this — v3 kernels add to compile time
  but are currently unreachable. Check whether `F_is_v3_enabled` is
  still hardcoded to `False` or has been enabled.
- `fmha_bwd.py` has 3 sub-kernel types with `@`-separated filters (3 parts).
- `fmha_fwd_splitkv.py` has 2 sub-kernel types (combine + splitkv) with
  `@`-separated filters (2 parts). The `@` split happens in
  `write_blobs`/`list_blobs`, not in the individual `get_*_blobs` functions.
- `fmha_batch_prefill.py` does not have arch-specific factories and its
  blob function does not accept a `targets` parameter.
- `fmha_fwd_splitkv.py` imports `FmhaFwdTileSize` from `fmha_fwd.py`.
- Factory class names vary: `KernelComponentFactoryBase`,
  `KernelComponentFactory`, `KernelComponentFactoryGfx9`, etc.
- `arch.py` provides `get_factories_for_targets()` which deduplicates
  factories and sorts by specificity (longest arch name first).
- `utils.py` provides `check_duplicates_and_paddings()` for validating
  trait ordering.
