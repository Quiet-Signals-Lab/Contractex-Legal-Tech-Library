# Privacy model

Every `LegalDoc` can carry a `PrivacyProfile`.  Before any built-in component
sends text to a model, `PrivacyAwareLLMRouter` reads the profile and either
blocks the call, rejects the provider, redacts the prompt, or lets it through.
The decision is made in code on every call.  It does not depend on the
application remembering to check a setting.

## Sensitivity levels

| `sensitivity` | Providers allowed | Before each call | When not allowed |
|---|---|---|---|
| `public` | any | nothing | — |
| `confidential` | any | PII detected and redacted in the prompt | — |
| `restricted` | `LocalProvider` only | PII detected and redacted in the prompt | `PrivacyRoutingError`, raised before the provider is called |
| `secret` | none | — | `PrivacyBlockedError`, raised before any prompt is built for a provider |

Routing is derived from sensitivity.  It can be overridden explicitly, for
example `PrivacyProfile(sensitivity="public", llm_routing="local_only")`.  A
document without a profile is treated as `public`; pass
`default_profile=` to the router to change that.

## Where it is enforced

- **Built-in tasks that call a model** get their provider through
  `LegalTask.llm_for(*docs)`, which wraps it in the router for the documents
  whose text goes into the prompt.  The comparison task passes both
  documents, so the stricter profile applies.
- **`TaskPipeline`** refuses to run any task with `requires_llm = True` on a
  blocked document.  This also covers custom tasks that declare it.
- **`LegalRAGPipeline`** stores each chunk's profile.  At query time it drops
  chunks the provider may never see, then sends the prompt through the router
  with the strictest profile among the chunks that remain.
- **Your own code** can call `router.route()` / `router.route_completion()`,
  or wrap a provider with `router.guard(provider, *docs)`.

Not enforced: calling `ContractExtractor`, the analysers or a provider
directly.  Those take text, not a document, so there is no profile to read.
Wrap the provider first, for example
`ContractExtractor(llm_provider=router.guard(llm, doc))`.

## Seeing what leaves the process

The provider below prints the prompt it receives instead of calling a model.
That makes it easy to check what a model would actually be sent.

```python
from contractex import LegalDoc
from contractex.llm.base import LLMProvider
from contractex.privacy import PIIDetector, PrivacyAwareLLMRouter, PrivacyProfile


class ShowPrompt(LLMProvider):
    """Prints each prompt and replies with a placeholder, like a model would."""

    context_window = 8_000
    model = "show-prompt"

    def complete(self, prompt, **kwargs):
        print("PROMPT:", prompt)
        return "Send notices to <EMAIL_ADDRESS_1>."

    def extract_structured(self, prompt, schema, **kwargs):
        print("PROMPT:", prompt)
        return schema()

    def estimate_cost(self, text):
        return 0.0

    def count_tokens(self, text):
        return len(text) // 4


text = open("examples/data/sample_nda.txt", encoding="utf-8").read()
notices = next(line for line in text.splitlines() if line.startswith("Notices"))

router = PrivacyAwareLLMRouter(detector=PIIDetector(use_presidio=False))
doc = LegalDoc(full_text=text, privacy_profile=PrivacyProfile(sensitivity="confidential"))

llm = router.guard(ShowPrompt(), doc)
print("ANSWER:", llm.complete("Who receives notices for Harbourline? " + notices))
```

```text
PROMPT: Who receives notices for Harbourline? Notices to Harbourline go to Priya Raman at <EMAIL_ADDRESS_1> or <PHONE_NUMBER_1>. Notices to Kestrel go to <EMAIL_ADDRESS_2>.
ANSWER: Send notices to priya.raman@harbourline.test.
```

The model sees placeholders.  The reply is restored locally, so the answer
contains the real address.  Streaming calls (`stream_complete`) are redacted
but not restored, because a placeholder can be split across tokens.

The same document marked `restricted` cannot go to a provider that is not a
`LocalProvider`:

```python
from contractex.privacy import PrivacyRoutingError

doc.privacy_profile = PrivacyProfile(sensitivity="restricted")
try:
    router.guard(ShowPrompt(), doc)
except PrivacyRoutingError as exc:
    print(exc)
```

```text
Document requires local-only routing but provider is 'ShowPrompt'.  Use contractex.llm.LocalProvider (Ollama).
```

## Detection

`PIIDetector` uses [Presidio](https://microsoft.github.io/presidio/) when the
`privacy` extra is installed, with Presidio's default spaCy model (download it
with `python -m spacy download en_core_web_lg`).  Otherwise it falls back to
regular expressions.

| Entity | Regex fallback | Presidio |
|---|---|---|
| `EMAIL_ADDRESS`, `PHONE_NUMBER` (US formats), `US_SSN`, `CREDIT_CARD`, `IBAN_CODE`, `PASSPORT_NUMBER`, `DRIVERS_LICENSE` (US) | yes | yes |
| `DATE_OF_BIRTH` | only after "born", "DOB" or "date of birth" | per Presidio's recognisers |
| `PERSON`, `LOCATION`, `NATIONAL_ID` | **no** | yes |

The fallback tolerates zero-width characters, Unicode dashes, fullwidth
digits and non-Latin letters in email addresses.  What it catches, and what it
misses, is measured in the [benchmarks](../benchmarks.md).

Add patterns for your own identifiers.  To make a task redact them too, give
it a router built on your detector:

```python
from contractex.llm import LocalProvider
from contractex.privacy.detector import RegexPIIRecognizer
from contractex.tasks import TaskPipeline
from contractex.tasks.summarization import SummarizationTask

detector = PIIDetector()
detector.add_recognizer(RegexPIIRecognizer(entity_type="MATTER_NO", pattern=r"MX-\d{6}"))
print([s.entity_type for s in detector.detect("Re matter MX-204518.")])

task = SummarizationTask(llm_provider=LocalProvider(model="llama3.1:8b"))
task.router = PrivacyAwareLLMRouter(detector=detector)
pipeline = TaskPipeline([task])
```

```text
['MATTER_NO']
```

## Redaction strategies

| `RedactionStrategy` | Replacement | Reversible |
|---|---|---|
| `REPLACE` (default) | `<PHONE_NUMBER_1>`; the same value always gets the same placeholder | yes, from the `RedactionMap` |
| `HASH` | `<PHONE_NUMBER_HASH:…>`, keyed HMAC-SHA256 | no |
| `MASK` | `***` | no |
| `ENCRYPT` | `<PHONE_NUMBER_ENC:…>`, AES-256-GCM (needs `cryptography`) | yes, with the key |

A `REPLACE` `RedactionMap` holds the original values in plaintext.  Store it
with the same protection as the document, never in a log.  Strategies can be
set per entity type with `PIIRedactor(strategy_overrides=...)`.

## Measuring it

`EvalHarness.run_privacy()` scores PII detection, redaction counts and
blocking decisions over a labelled suite (see [Evaluation](evaluation.md)).
The [benchmarks](../benchmarks.md) include a routing matrix that checks every
sensitivity level against a cloud and a local provider through each entry
point above.

## Limits

- The router trusts the profile.  Classifying a document's sensitivity is the
  caller's job.
- `local_only` means "a `LocalProvider` instance".  The router does not check
  where that provider's Ollama host runs.
- Without Presidio, names, places and national identifiers are not detected,
  so they reach the model in `confidential` prompts.
- Only text that goes through the router is protected.  See
  [Limitations](../limitations.md) for the full list.
