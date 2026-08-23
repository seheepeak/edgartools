# Local edgartools integration

This fork supplies the Markdown and section-source APIs consumed by Max. The
consumer selects this repository through `tool.uv.sources`. The package version
is 5.55.0; installation is non-editable.

## Markdown tables

The renderer emits a valid GFM delimiter row for headerless tables, preserving
all source rows. A table cell joins its internal lines so a literal line break
cannot turn one cell into several Markdown rows. Cell text is retained rather
than truncated. Tables, headings and code are not paragraph-wrapped.

`MarkdownRenderer(wrap_width=None)` reads `EDGAR_MARKDOWN_WRAP_WIDTH` as a
fallback. Unset, invalid or non-positive values disable wrapping. Max configures
this value to its staged-document wrap width.

A remaining renderer limitation is that mixed child nodes may join a table or
heading to the preceding paragraph. A consumer must preserve the rendered text
when projecting section headings onto it.

## Section identity and rendering

On forms with unique Item numbers, TOC attribution uses the schema's canonical
Part when an earlier Part heading is stale. This applies with source tracking
both enabled and disabled. Form 10-Q retains Part-specific Item identities.

Page-index sections render their lazy HTML page slice, retaining table structure.
An exception or empty Markdown result falls back to `Section.text()`, as on the
TOC rendering path. Index sections can legitimately have no DOM coordinates.

## Source coordinates

`ParserConfig(track_source=True)` retains the parser's processed DOM. Tracking is
opt-in; empty anchor-bearing tags survive preprocessing in that mode. The exact
input, including authoring-tool comments, remains in `metadata.original_html`.

Builder nodes carry element ordinals. Pattern sections expose `source_start` and
`source_end` in the retained DOM's coordinate system; both use the same heading
normalization. Inline headings stay within their own block or cell and cannot
climb into a wrapper holding earlier visible text. The retained DOM and its
indexes must not be mutated during extraction.

`source_end` is part of the consumed span API: Max uses it, together with the next
Item's start and TOC anchors, to bound eligible navigation targets. Max projects
those targets onto its existing Markdown rather than re-rendering Item slices.
Source positions also bound cover extraction. Generic `start_offset`/`end_offset`
fields belong to individual detectors and are not DOM ordinals.

The tracking contract is section identity and honest source coordinates, not an
identical node count: preserving empty anchors can add nodes. A missing source
API is an explicit installation error in Max.

## Consumer integration

Max's staging, chunk naming and report policies are documented in its
`max/CLAUDE.md`. They are not part of this fork's parsing API.

## Anchor integrity and numbered-index rejection

Text normalization operates outside complete markup tags. Attribute values,
including punctuation and whitespace in ids/hrefs, survive encoding, entity,
whitespace and punctuation cleanup in both source-tracking modes.

Bare-number TOC rows respect a preceding Notes-on/to-financial-statements header,
even after introductory rows. Linked Notes entries remain ordinary navigation
entries rather than changing the index scope. Only labels at or before the
number column affect its interpretation; Notes/Exhibits in a later title column
do not. A later Item column resets the index scope. Page
footer numbers next to prose references do not become Items. Pattern detection
also excludes inline heading fragments immediately preceded by "see" or "refer
to" in the same paragraph; the text remains in the document.

## Installation and checks

After a fork edit, reinstall in the consumer:

```bash
cd ~/.openclaw
uv sync --reinstall-package edgartools
```

A plain `uv sync` can reuse a cached wheel. Focused offline source tests are in
`tests/test_section_source_positions.py`, `tests/test_toc_agents.py`,
`tests/test_filing_anchor_integrity.py`, and the
`TestMakeSectionKeyValidity`/`TestTenQUnaffected` classes in
`tests/issues/regression/test_issue_836_spurious_part_iv_items.py`.

Consumer checks are in `max/tests/test_edgar.py` and
`max/tests/test_edgar_partition.py`, plus the final correctness gates in
`max/tests/test_edgar_closure.py`. Its fixture audit is:

```bash
python -m max.tests.edgar_audit --fixtures ~/workspace/edgartools/tests/fixtures/html
```

For an upstream update, rebase the fork, inspect changes to these interfaces,
reinstall it in Max, and run the renderer and consumer checks before use.
