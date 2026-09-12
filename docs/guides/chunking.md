# Chunking and provenance

## `ClauseAwareChunker`

The text is cut into sections at lines that start a heading, and consecutive
sections are packed into chunks of at most `max_chunk_size` tokens.  Tokens
are estimated as characters ÷ 4, not counted by a model tokenizer.  With no
headings, the text is cut at blank lines instead.  A section too large for one
chunk is split at sentence ends, and a sentence too large at spaces.

Lines recognised as headings (leading whitespace allowed):

| Pattern | Examples |
|---|---|
| Number, dot, then a capital, `(` or quote | `1. Term`, `2.1 Scope`, `10. Payment`, `1.1 "Affiliate" means` |
| `Article` or `Section` and a number, any case | `Article 4`, `SECTION 5` |
| Letter or number in brackets | `(a)`, `(B)`, `(12)` |
| A word followed by `TERMINATION` in capitals | `EARLY TERMINATION` |

Not recognised: unnumbered headings in capitals (`GOVERNING LAW`), `WHEREAS`,
and roman numerals in brackets such as `(iv)`.  A line like `10. million
units` (lower case after the number) is not a heading.

Guarantees, checked by the test suite over seeded random documents:

- every chunk is an exact substring of the input;
- no chunk exceeds `max_chunk_size`;
- no chunk starts or ends mid-word, except a single word longer than the
  limit, which is cut;
- a heading stays in the same chunk as the start of its body;
- with `overlap > 0`, each chunk after the first starts with up to `overlap`
  tokens from the end of the previous chunk, beginning at a sentence or word
  boundary, when that still fits.

```python
from contractex.chunking import ClauseAwareChunker

text = open("examples/data/sample_nda.txt", encoding="utf-8").read()
chunker = ClauseAwareChunker(max_chunk_size=80, overlap=0)
chunks = chunker.chunk(text)

print(len(chunks), max(chunker.count_tokens(c) for c in chunks))
print(all(c in text for c in chunks))
print([c.splitlines()[0] for c in chunks])
```

```text
6 72
True
['MUTUAL NON-DISCLOSURE AGREEMENT', '1. Definitions.', '2. Obligations.', '3. Term.', '5. Notices.', '6. Governing Law.']
```

The first chunk holds the title, the parties and the recital, which come
before the first numbered heading.

## `SemanticChunker`

This one packs paragraphs, or sentences with `split_on="sentence"`, into
chunks of about `max_chunk_size` tokens.  Two differences from
`ClauseAwareChunker` matter.  First, it does not enforce the size limit on a
single long paragraph or sentence.  Second, it re-joins the pieces it packs,
so its chunks are not exact substrings of the input and cannot be located
with `source_text` below.

## `ProvenanceTracker`

Register the chunks together with the text they came from, then resolve any
value back to character offsets in that text:

```python
from contractex.utils.provenance import ProvenanceTracker

tracker = ProvenanceTracker(source_url="examples/data/sample_nda.txt")
tracker.register_chunks(chunks, source_text=text)

span = tracker.find_span("thirty (30) days' written notice")
print(span.char_start, span.char_end, repr(text[span.char_start : span.char_end]))

print(tracker.find_span("30 days written notice"))
```

```text
882 914 "thirty (30) days' written notice"
None
```

The lookup first tries an exact substring match.  If that fails, it falls back
to token overlap between the value and a whole chunk, which rarely reaches the
0.85 threshold.  In practice, a paraphrased value (the second lookup) does not
resolve.  The [benchmarks](../benchmarks.md) measure how often values resolve
verbatim, with whitespace collapsed, and lower-cased.

Without `source_text`, the offsets assume the chunks tile the document with
one character between them.  No chunker in this package produces that, so
always pass `source_text`.

`ContractExtractor` does not attach source spans to what it extracts.  Run
the tracker over its output values if you need them.
