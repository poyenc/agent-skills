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
- [Scroll aids for wide/long tables](#scroll-aids-for-widelong-tables)
- [Status marks and chips](#status-marks-and-chips)
- [Pillar callout](#pillar-callout)
- [ASCII diagram block](#ascii-diagram-block)
- [Footer](#footer)
- [Editorialize vs faithful](#editorialize-vs-faithful)
- [Citations, terminology, and audience](#citations-terminology-and-audience)
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

For a matrix table wider than the viewport (many status columns — e.g. comparing 4+ variants),
freeze the identity column so the reader never loses row context while scrolling sideways:

```css
.sticky-col{position:sticky;left:0;z-index:2;background:var(--paper);box-shadow:1px 0 0 0 var(--rule-strong);}
tbody tr:hover td.sticky-col{background:var(--code-bg);}
th.sticky-col{z-index:3;}
```

Apply `sticky-col` alongside `feat` (or `k` for a normal table's leading column) on both the
`<td>` in every row and the matching `<th>` in `<thead>` (and `<tfoot>`, see below). When a
row name is itself a defined entity backed by a source (a parameter, an API, a spec item),
hyperlink the row label to that definition — not just the citations elsewhere in the row — so
a skimming reader can jump straight to ground truth.

## Scroll aids for wide/long tables

A native horizontal scrollbar sits at the bottom of a table's viewport — useless on a long
table, since reaching it means scrolling past every row first. For any table wide enough to
need horizontal scrolling, add a synced scroll strip above it and wire it up with a small
script (this is the one exception to "no JS beyond the scroll-spy" — it's still pure
navigation, no charting or data logic):

```css
.tbl-scroll-top{overflow-x:auto;overflow-y:hidden;height:14px;margin:1.6rem 0 0;}
.tbl-scroll-top > div{height:1px;}
.tbl-wrap{overflow-x:auto;margin:0.4rem 0 1.6rem;} /* tighten the top margin to sit right under the scroll strip */
```

```js
document.querySelectorAll('.tbl-wrap').forEach(function (wrap) {
  var table = wrap.querySelector('table');
  var topScroller = document.createElement('div');
  topScroller.className = 'tbl-scroll-top';
  var spacer = document.createElement('div');
  topScroller.appendChild(spacer);
  wrap.parentNode.insertBefore(topScroller, wrap);
  var syncing = false;
  function sync() { spacer.style.width = table.scrollWidth + 'px'; }
  sync();
  window.addEventListener('resize', sync);
  topScroller.addEventListener('scroll', function () {
    if (syncing) return; syncing = true; wrap.scrollLeft = topScroller.scrollLeft; syncing = false;
  });
  wrap.addEventListener('scroll', function () {
    if (syncing) return; syncing = true; topScroller.scrollLeft = wrap.scrollLeft; syncing = false;
  });
});
```

For a table long enough that its `<thead>` scrolls off-screen, repeat the header row as a
`<tfoot>` — same cells, styled with a top divider instead of a bottom one, so column identity
survives scrolling to the end:

```css
tfoot th{border-bottom:none;border-top:1px solid var(--rule-strong);}
```

```html
<tfoot><tr><th class="feat sticky-col">Feature</th><th class="c">A</th></tr></tfoot>
```

Both aids are opt-in, layered on top of the base `.tbl-wrap`/`table`/`table.matrix` components
above — add them when a table is wide or long enough that the reader would otherwise lose
context, not by default on every table.

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

## Citations, terminology, and audience

These apply whenever the source material makes verifiable technical claims — a research
report, an evidence-backed review, a feature/spec comparison:

- **When citing a version-controlled source, link every file/line citation, pinned to a
  commit.** This applies only when the doc's claims are backed by facts in a git-hosted
  codebase — it doesn't apply to specs, policy docs, meeting notes, or other technical docs
  with no repo behind them. When it does apply: resolve the citing repo's current commit and
  turn every `path/to/file.ext:123` (or bare filename) mention into a line-addressable
  permalink for whatever host is in use — GitHub's `blob/<sha>/path#L123`, GitLab's
  equivalent, or the host's native line-anchor scheme — for every occurrence, not just the
  first. A file or function that doesn't exist yet (proposed/future work) stays plain text;
  there's nothing on the other end to verify.
- **Use the domain's own terms — never invent a label.** Describe a parameter, mechanism, or
  component by the name the source actually uses for it, not a coined shorthand, nickname, or
  abbreviation. An invented term can't be grepped back to source and forces the reader to
  guess the mapping themselves.
- **Scrub local/scratch references before treating a doc as external-facing.** When the user
  says "for outside readers" or the doc will leave the authoring machine/session, grep the
  draft for local absolute paths (`~/`, `/home/`, `/Users/`), working-file names (ledgers,
  scratch notes, internal task/process docs), and links into internal-only or scratch
  branches. Replace with plain prose or a canonical link into the actual product source —
  never a path or link only the author's environment can resolve.
- **A rename/terminology-fix request means a full sweep, verified.** When told to replace a
  placeholder or fix a term, grep the whole document for every form of the old term before
  declaring done — don't rely on remembering where it appeared. This includes headers and
  section titles that used the placeholder as a proper noun, not just the spot the user
  pointed at.

## Escaping and correctness

- Escape `<`, `>`, `&` that are literal content (common in code/templates like
  `std::conditional_t<...>` → `std::conditional_t&lt;...&gt;`). The reference does this.
- Preserve every fact, number, and file:line citation exactly — this style is used for
  source-verified technical docs, so silent "cleanup" of a value is a real defect.
- Keep the reading-measure clamp (`--measure`) unless a table needs `sec wide`.
- Before finishing, sanity-check that every TOC `href` has a matching section `id` and vice
  versa, and that the document is a single self-contained file.
