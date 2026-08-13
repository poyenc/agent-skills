# Component kit

The visual system is fixed by `template.html` (its CSS is the contract). Your job is to
pour content into that shell using the class names below. Do not invent new CSS or restyle
unless the user explicitly asks — the whole point is that every document looks like it came
from the same hand. If a piece of content has no matching component here, prefer plain
`<p>`, `<ul class="clean">`, or a table over inventing a new visual treatment.

## Contents
- [The shell you fill](#the-shell-you-fill)
- [Header block](#header-block)
- [Sections and the TOC](#sections-and-the-toc)
- [Text: paragraphs, lists, captions](#text-paragraphs-lists-captions)
- [Tables (normal and matrix)](#tables-normal-and-matrix)
- [Status marks and chips](#status-marks-and-chips)
- [Pillar callout](#pillar-callout)
- [ASCII diagram block](#ascii-diagram-block)
- [Footer](#footer)
- [Editorialize vs faithful](#editorialize-vs-faithful)
- [Escaping and correctness](#escaping-and-correctness)

---

## The shell you fill

`template.html` has two holes:
- `<!-- TOC_ITEMS -->` inside `<nav class="toc"><ol>` — the contents rail.
- `<!-- MAIN_CONTENT -->` inside `<main>` — the `<header>` then the sections.

Also replace `{{TITLE}}` in `<title>` with the document title (plain text, no HTML).
Keep the `<script>` and everything else verbatim. The scroll-spy script wires itself to
`.toc a` and `.sec` automatically, so as long as your TOC links point at section ids, the
active-section highlight just works.

## Header block

Goes first inside `<main>`, before any `<section>`. Parts are optional — use what the
source gives you. `eyebrow` = a short kicker; `thesis` = the one-paragraph "what this is";
`meta` = the front-matter (date, scope, sources, etc.) as a definition list.

```html
<header>
  <p class="eyebrow">Short kicker · Category</p>
  <h1>The document title</h1>
  <p class="thesis">
    One tight paragraph stating what this document is and why it exists.
    Use <b>bold</b> for the load-bearing phrases — it renders in the accent color.
  </p>

  <dl class="meta">
    <dt>Date</dt><dd>2026-07-12</dd>
    <dt>Scope</dt><dd>What is and isn't covered</dd>
    <dt>Sources</dt><dd>Where this came from, with <code>inline code</code> as needed</dd>
    <dt>Method</dt><dd class="ok">Highlight one meta line with class "ok" (accent) if it deserves emphasis</dd>
  </dl>
</header>
```

If the source opens with a `key: value` front-matter block or a bulleted "Audience / Scope /
Date" preamble, that is exactly what `dl.meta` is for.

## Sections and the TOC

Every top-level heading becomes a `<section class="sec" id="...">`. Give each a stable,
lowercase, hyphenated `id` derived from its title. The `<h2>` carries an optional number
chip via `<span class="num">`.

```html
<section class="sec" id="overview">
  <h2><span class="num">1</span>Overview</h2>
  <!-- section body -->
</section>
```

Add the matching TOC entry (in document order):

```html
<li><a href="#overview"><span class="n">1</span>Overview</a></li>
```

Notes:
- Keep TOC labels short — trim long section titles to a few words. The `n` span is the
  number/letter (use `A`, `B` … for appendices, like the reference did).
- A section that holds a very wide table can opt out of the reading-measure clamp with
  `class="sec wide"` so the table can use the full width.
- Number sections only if the source does; unnumbered sections are fine — just omit the
  `<span class="num">`/`<span class="n">`.

## Text: paragraphs, lists, captions

```html
<p>Body text. Stays within a comfortable reading measure automatically.</p>
<p class="small muted">Secondary note — smaller and greyed, good for table captions.</p>

<p class="cap">Label above a block</p>   <!-- uppercase micro-label -->

<ul class="clean">
  <li><b>Term</b> — explanation. The dash bullet is drawn by CSS; don't type it.</li>
  <li>Nested lists switch to a middot bullet automatically:
    <ul class="clean"><li>sub-point</li></ul>
  </li>
</ul>
```

Wrap a run of paragraphs in `<div class="flow"> … </div>` when you want even vertical
rhythm between them (it spaces direct children). Plain `<p>` is fine otherwise.

## Tables (normal and matrix)

Always wrap tables in `<div class="tbl-wrap">` so they scroll on narrow screens.

Normal table — for detail rows with a leading key column. Use `<td class="k">` for that
first cell (renders in accent, no wrap), and `<b>` for emphasis inside cells.

```html
<div class="tbl-wrap"><table>
  <thead><tr><th>#</th><th>Variant</th><th>Notes</th></tr></thead>
  <tbody>
    <tr><td class="k">M1</td><td><b>Name</b></td><td>Detail with <code>code</code></td></tr>
  </tbody>
</table></div>
```

Matrix table — for a feature × option grid with compact centered status cells. Add
`class="matrix"`; mark the first column `feat` and every status column/header `c`.

```html
<div class="tbl-wrap"><table class="matrix">
  <thead><tr>
    <th class="feat">Feature</th><th class="c">A</th><th class="c">B</th>
  </tr></thead>
  <tbody>
    <tr><td class="feat">No mask</td><td class="c yes">✓</td><td class="c no">✗</td></tr>
  </tbody>
</table></div>
```

## Status marks and chips

Status colors (use inside table cells or inline text): `yes` (green), `no` (red),
`warn` (amber), `na` (grey, for "not applicable" — pair with an em dash `—`).

```html
<span class="yes">✓</span>  <span class="no">✗</span>
<span class="warn">~</span> <span class="na">—</span>
```

A status cell often carries a short qualifier, not just the bare mark — keep the color on
the mark and let the rest be plain text in the same cell. This is common and correct:

```html
<td class="c no">✗ never emitted</td>
<td class="c warn">~ dense = 0.0</td>
<td class="c yes">✓¹</td>          <!-- footnote marker; define it in a small muted note below -->
```

Classification chips — small labels for tagging a row/thing:

```html
<span class="chip">runtime</span>            <!-- neutral -->
<span class="chip ind">compile-time</span>   <!-- accent: "independent / primary" -->
<span class="chip dead">dead</span>          <!-- red: "removed / not emitted" -->
```

Use one consistent vocabulary of chip labels within a document. Don't introduce a chip
color beyond these three.

When a single cell holds a *combined* classification (e.g. "runtime in one mode, compile-time
in another"), stack the chips in priority order and follow with any clarifying text, rather
than forcing one label:

```html
<td><span class="chip ind">compile-time</span> <span class="chip">runtime</span> depends on mode</td>
```

## Pillar callout

The one "highlight" device. Use it for a thesis, a key correction, or a tier/priority
callout — a claim you want to stop the reader on. Don't overuse it; a few per document.

```html
<div class="pillar">
  <p class="plabel">Label — the point in a few words</p>
  <p>The statement itself. Keep it to a sentence or three.</p>
</div>
```

## ASCII diagram block

For monospace diagrams, trees, or preformatted layouts. `white-space:pre` is preserved.
`accent` and `dim` spans let you color parts.

```html
<div class="diagram">root
├── <span class="accent">important</span>
└── <span class="dim">de-emphasized</span></div>
```

There are no chart/graph components by design — represent structure with tables or this
diagram block, never an image or JS chart.

## Footer

Optional closing block for provenance, a one-line summary, or a legend of the chips used.

```html
<footer class="foot">
  <p>One-line summary or provenance note.</p>
  <p>Legend: <span class="chip ind">compile-time</span> own path ·
     <span class="chip">runtime</span> shared path · <span class="chip dead">dead</span> not emitted.</p>
</footer>
```

---

## Editorialize vs faithful

The skill asks the user which mode to use per document, because the right amount of
restructuring depends on the content and the stakes.

**Editorialize** — reshape the raw content into the component kit so it reads like the
reference document:
- Opening front-matter / preamble → `eyebrow` + `h1` + `thesis` + `dl.meta`.
- A short list of ✓/✗/⚠ or yes/no/partial values → a `matrix` table with status colors.
- Words like "supported / not / partial / n-a" → `yes` / `no` / `warn` / `na`.
- A classification or status word attached to items → a `chip` (`ind`/plain/`dead`).
- The single most important claim, correction, or recommendation of a section → a `pillar`.
- Preformatted trees or layouts → a `diagram` block.
This is the default feel of the house style, but never invent facts to fill a component —
if the source doesn't support a chip/pillar, use plain text.

**Faithful** — map the source's own structure 1:1 into the styled shell and stop there:
- Headings → sections + TOC; paragraphs → `<p>`; lists → `ul.clean`; tables → styled
  tables; fenced code → `code` / `diagram`.
- Do NOT promote anything to a pillar, invent chips, or colorize marks that aren't already
  in the source. If the source literally contains ✓/✗, you may still apply the status
  colors, since that's presentation of an existing mark, not new editorial content.
Choose this for correctness-critical documents where added interpretation is a liability.

## Escaping and correctness

- Escape `<`, `>`, `&` that are literal content (common in code/templates like
  `std::conditional_t<...>` → `std::conditional_t&lt;...&gt;`). The reference does this.
- Preserve every fact, number, and file:line citation exactly — this style is used for
  source-verified technical docs, so silent "cleanup" of a value is a real defect.
- Keep the reading-measure clamp (`--measure`) unless a table needs `sec wide`.
- Before finishing, sanity-check that every TOC `href` has a matching section `id` and vice
  versa, and that the document is a single self-contained file.
