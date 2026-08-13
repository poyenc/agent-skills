---
name: write-html-doc
description: >
  Produce a single self-contained HTML technical document in a fixed house style —
  light "paper" theme, all IBM Plex Mono, a sticky sidebar table-of-contents with
  scroll-spy, and tables / callouts / status chips instead of charts. Works two ways:
  convert an existing Markdown (or any readable text/source) file to HTML, or write the
  HTML straight from the current conversation. Use this skill whenever the user wants a
  technical doc, report, feature matrix, comparison, spec, or notes turned into a polished
  shareable HTML page or "deliverable", or says things like "make an HTML version of this",
  "turn this markdown into a webpage", "write this up as an HTML doc", "styled HTML report",
  "monospace doc with a sidebar TOC", or "render this as a nice single-file HTML". Prefer
  this over ad-hoc HTML any time the goal is a clean, consistent technical document.
---

# Write HTML technical document

Turn content into one polished, self-contained HTML file in a fixed house style. The look
is not up for negotiation on each run — it is defined by `references/template.html`, whose
CSS you copy verbatim. Your work is deciding what content goes where and pouring it into the
shell with the right components. This keeps every document visually identical while the
content varies, which is the whole point of a house style.

## What the style is (so you can recognize a good result)

Light near-white background, everything set in IBM Plex Mono (loaded from Google Fonts with
a system-monospace fallback), a 220px sticky left sidebar table-of-contents that highlights
the section you're reading, a comfortable reading measure, and a small kit of components —
header block, sections, tables (including a compact "matrix" grid), status marks in
green/red/amber, classification chips, "pillar" callouts, and monospace ASCII diagrams.
There are deliberately **no charts, no images, no JS beyond the scroll-spy, and no dark
theme** — structure is carried by tables and callouts.

## Inputs

Two modes, detected from the request:
- **From a file** — the user points at a `.md` or any readable text/source file. Read the
  whole file first.
- **From context** — no source file; build the document from what the conversation already
  contains.

## Workflow

1. **Get the content.** In file mode, read the entire source. In context mode, gather the
   material from the conversation. Never work from a skim — missing a table or a caveat
   shows up directly in the output.

2. **Choose the conversion mode — ask the user, unless they already said.** The right amount
   of restructuring depends on the content and the stakes, so confirm per document:
   - **Editorialize** — reshape into the component kit (front-matter → header + meta,
     ✓/✗/partial → a status matrix, key claims → pillar callouts, classifications → chips).
     This produces the richest result and matches the reference document's feel.
   - **Faithful** — map the source's own structure 1:1 into the styled shell, adding no
     callouts or chips that aren't in the source. Right for correctness-critical documents
     where added interpretation is a liability.
   Ask a single quick question ("Editorialize into the full component kit, or a faithful
   structural conversion?") and proceed. If the user already indicated which they want, or
   the intent is obvious (e.g. "just convert it, don't editorialize"), skip the question.

3. **Confirm the output path.** Default to `<stem>.html` next to the source (e.g.
   `report.md` → `report.html`); in context mode, propose a sensible name in the working
   directory. State the path you'll write and let the user override it with any path/name.
   If a file already exists at that path, warn and get confirmation before overwriting —
   losing a previous deliverable is exactly the kind of thing to avoid.

4. **Build the document.** Read `references/components.md` for the exact HTML of every
   component and the editorialize-vs-faithful mapping rules. Then:
   - Start from `references/template.html`. Copy it verbatim; replace `{{TITLE}}`, fill the
     `<!-- TOC_ITEMS -->` list, and fill `<!-- MAIN_CONTENT -->`. Do not touch the CSS or
     the scroll-spy script.
   - Give every section a stable `id`; make the TOC links point at those ids (the scroll-spy
     wires itself up automatically).
   - `references/example.html` is a small worked example in the finished style — skim it if
     you want to see the components used together.

5. **Verify before declaring done.** Open your reasoning to these checks, because they are
   the usual failure modes:
   - Every TOC `href` has a matching section `id`, and every section is in the TOC.
   - Literal `<`, `>`, `&` in content (e.g. C++ templates, HTML snippets) are escaped.
   - Every fact, number, and file:line citation from the source is preserved exactly — this
     style is used for source-verified docs, so a dropped or altered value is a real defect.
   - It's a single self-contained file (only external dependency is the Google Fonts link).
   Then report the written path.

## Adapting the style

The template is the locked default. If — and only if — the user explicitly asks for a
deviation (a wider layout, an extra chip meaning, a different accent color, etc.), make the
minimal change needed and keep everything else identical. Absent such a request, do not
restyle, add libraries, or "improve" the CSS.
