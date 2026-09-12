# Quick start

Steps 1 to 3 need only `pip install contractex`: no model, no network, no API
key.  Step 4 calls a model.  It uses a local model through
[Ollama](https://ollama.com), which needs `pip install "contractex[ollama]"`,
Ollama running, and `ollama pull llama3.1:8b`.

The examples read [`examples/data/sample_nda.txt`](https://github.com/Quiet-Signals-Lab/Contractex-Legal-Tech-Library/blob/main/examples/data/sample_nda.txt),
a short fictitious NDA.  Every block on this page is executed by the test
suite, and the output shown is what it prints.

## 1. Parse the structure

Section numbering, defined terms and cross-references are found by
deterministic parsing.

```python
from contractex.structure import parse_structure

text = open("examples/data/sample_nda.txt", encoding="utf-8").read()
structure = parse_structure(text)

for section in structure.sections:
    print(f"{section.number} {section.title}".strip())
print(sorted(structure.defined_terms))
print("Unresolved:", [ref.raw_text for ref in structure.unresolved_refs])
```

```text
MUTUAL NON-DISCLOSURE AGREEMENT
1 Definitions.
2 Obligations.
3 Term.
4 Exceptions.
5 Notices.
6 Governing Law.
['Agreement', 'Confidential Information', 'Harbourline', 'Kestrel', 'Purpose', 'Representatives']
Unresolved: ['Section 9']
```

The NDA refers to a Section 9 that does not exist.  The parser reports it
instead of guessing.

## 2. Find and redact personal data

```python
from contractex.privacy import PIIDetector, PIIRedactor

detector = PIIDetector()
spans = detector.detect(text)
print("Presidio:", detector.using_presidio)
for span in spans:
    print(span.entity_type, span.text)

redacted = PIIRedactor().redact(text, spans)
print(next(line for line in redacted.text.splitlines() if line.startswith("Notices")))
```

```text
Presidio: False
EMAIL_ADDRESS priya.raman@harbourline.test
PHONE_NUMBER 415-555-0132
EMAIL_ADDRESS legal@kestrelpoint.test
Notices to Harbourline go to Priya Raman at <EMAIL_ADDRESS_1> or <PHONE_NUMBER_1>. Notices to Kestrel go to <EMAIL_ADDRESS_2>.
```

This output comes from the regex fallback, which is what runs when
[Presidio](https://microsoft.github.io/presidio/) is not installed.  It catches
the email addresses and the phone number but not the name "Priya Raman": the
fallback has no name recogniser.  Install `contractex[privacy]` if names must
be redacted.  See [Limitations](../limitations.md).

## 3. Chunk and trace a value to its source

`ClauseAwareChunker` cuts at section headings, and every chunk is an exact
substring of the document.  `ProvenanceTracker` resolves a value (for example,
one an LLM returned) to character offsets in the original text.

```python
from contractex.chunking import ClauseAwareChunker
from contractex.utils.provenance import ProvenanceTracker

chunks = ClauseAwareChunker(max_chunk_size=120, overlap=0).chunk(text)
for chunk in chunks:
    print(chunk.splitlines()[0])

tracker = ProvenanceTracker()
tracker.register_chunks(chunks, source_text=text)
span = tracker.find_span("governed by the laws of the State of Delaware")
print(span.char_start, span.char_end, text[span.char_start : span.char_end])
```

```text
MUTUAL NON-DISCLOSURE AGREEMENT
1. Definitions.
3. Term.
6. Governing Law.
1245 1290 governed by the laws of the State of Delaware
```

## 4. Run tasks under a privacy profile

A `LegalDoc` carries a `PrivacyProfile`.  Every built-in task that calls a
model goes through the privacy router, which enforces the profile on each
call.

```python
from contractex import LegalDoc
from contractex.core.legal_document import DocType
from contractex.llm import LocalProvider
from contractex.privacy import PrivacyProfile
from contractex.tasks import TaskRegistry

doc = LegalDoc(
    doc_type=DocType.CONTRACT,
    full_text=text,
    privacy_profile=PrivacyProfile(sensitivity="restricted"),
)
llm = LocalProvider(model="llama3.1:8b")

pipeline = TaskRegistry.default().build_pipeline(
    ["pii_detection", "classification", "summarization"],
    task_kwargs={"summarization": {"llm_provider": llm}},
)
result = pipeline.run(doc)
print(sorted(result.extracted))
print(result.extracted["cuad_labels"])
```

```text
['_task_timings', 'cuad_labels', 'pii_spans', 'summary']
['confidentiality', 'governing_law']
```

`restricted` means only a `LocalProvider` may see the document, and PII is
redacted from each prompt before the call.  The summary is model output and is
not shown here.

If the same document were `secret`, no task that calls a model would run:

```python
from contractex.privacy import PrivacyBlockedError

doc.privacy_profile = PrivacyProfile(sensitivity="secret")
try:
    pipeline.run(doc)
except PrivacyBlockedError as exc:
    print(type(exc).__name__)
```

```text
PrivacyBlockedError
```

## Next

- [Privacy model](../guides/privacy.md): the four sensitivity levels and what each enforces.
- [Tasks](../guides/tasks.md): which tasks call a model and what happens when the output is poor.
- [LLM providers](../guides/providers.md): configuring OpenAI, Anthropic, Google or Ollama.
