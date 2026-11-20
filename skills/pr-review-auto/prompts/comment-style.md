# Comment style (pr-review-auto)

How to write the text of each review comment and reply. This file covers only how a comment's
text is written; placement and posting follow the lead's policy.

A comment is useful to the extent it saves the author time. Whoever found the issue already
located the exact line, understood the mechanism and worked out a fix; the comment hands all of
that over so the author does not have to redo the investigation. Write it as a careful
colleague would, to help, not to flag.

## Content

- Say only what the author needs to understand the issue and act on it. Default shape: two short
  paragraphs. First what happens in the code (the mechanism and its concrete consequence, not
  just "this is wrong"), then the fix, or the question that resolves it. A third part (why the
  old code was fine, or what exactly changes that) belongs only when the issue cannot be
  understood without it.
- Every sentence must change what the author does next. Cut anything that only restates the
  diff or the location the comment is attached to, filler ("it's worth noting that", "this is
  important because"), and hedges on facts you confirmed. If a sentence adds nothing the one
  before it did not, delete it.
- A defect repeated at several places: describe it at the anchor site and add one short "Also
  at A, B, C" line with links. Do not narrate every occurrence.
- State verified facts plainly. Hedge only what cannot be checked from the code: whether a
  tradeoff was deliberate, whether something was already measured or considered, whether a
  future case is planned. Ask such a point as a direct, answerable question ("was this measured
  with the new flag?"), not as a disclaimer on a confirmed fact.
- Pin the fix to an exact place, concrete enough to apply without further investigation. When
  the fix belongs somewhere other than the line the comment is attached to (another function or
  file), say exactly where, and why there rather than the more obvious spot.
- No severity, confidence or priority in the text.

## Links

- Every reference to code other than the line the comment is attached to (another function, a
  related test, a call site, even a line a few lines away in the same function) is a markdown
  link to the GitHub blob permalink at the reviewed commit:
  `[label](https://github.com/<owner>/<repo>/blob/<reviewed commit SHA>/<path>#L<line>)`, or
  `#L<start>-L<end>` for a range. Never a bare `file.py:123` reference.
- The link label names what the reader cares about: the identifier of the function, method or
  class it points at (`` [`_is_mode_write()`](...) ``, `` [`FooClass`](...) ``). Use
  `path:line` as the label only when there is no single named construct (an import line, a
  block of statements).
- A comment not attached to the line it is about (a file-level comment, a standalone comment,
  or an item in a consolidated comment) starts with its location on its own line:
  `**Location:** [label](permalink)`, with the same label rule.

## Form

- A code snippet, example, suggested fix or command (anything meant to be read as code or run,
  not as prose) goes in its own fenced code block with a language tag, on its own lines,
  separated from the explanation by blank lines. Never inline it into a sentence.
- For a direct fix, show a snippet the author can copy. For a conceptual fix, show the key
  statements before and after, but only when that clarifies the fix; a one-line description of
  the change is enough when there is no code shape worth showing.
- Use normal fenced code blocks. Never use GitHub `suggestion` blocks.
- Never leak internal process: no local file paths, hostnames, machine or session identifiers,
  names of reviewing agents or tools, or how the finding was produced (verification passes,
  review rounds, reports). Public GitHub links (blob permalinks, PR and issue URLs) are fine.
- This is a review comment, not a chat message: no reply-style or conversational framing such as
  "Re:", "FYI" or "Just noting". Use no abbreviation unless it is a well-known term already used
  in the repository; spell things out.
