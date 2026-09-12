# Tasks and pipelines

A task takes a `LegalDoc` and returns it with results added under
`doc.extracted[<key>]`.  `TaskPipeline` runs tasks in order.  Each task
declares `requires_llm`, which marks the deterministic/probabilistic boundary.
The pipeline uses it to refuse model-calling tasks on
[blocked documents](privacy.md).

## Built-in tasks

| `task_id` | Calls a model | Output key | How it works | When the output is poor |
|---|---|---|---|---|
| `pii_detection` | no | `pii_spans` | Presidio, or the regex fallback; also sets `doc.privacy_profile` | Missed PII stays in the text.  See [Limitations](../limitations.md). |
| `citation` | no | `citations` | Regular expressions for US case citations, U.S.C., C.F.R., EU regulations and directives, and acronyms such as GDPR | Other citation formats are silently absent. |
| `classification` | no | `cuad_labels` | Keyword matching against CUAD clause types | A label means an indicative phrase occurs, not that the clause exists. |
| `ner` | no | `ner_entities` | spaCy (`contractex[spacy]` plus a spaCy model) | As good as the spaCy model. |
| `summarization` | yes | `summary` | One completion over the first 12,000 characters | Returned as-is; nothing is validated.  Longer documents are truncated. |
| `timeline` | yes | `timeline` | One structured call over the first 12,000 characters | Output that does not fit the schema raises an error; nothing is repaired. |
| `obligations` | yes | `obligations` | One structured call over the first 12,000 characters | As for `timeline`. |
| `comparison` | yes | `comparison` | One structured call over the first 8,000 characters of each document (`doc_b=` keyword) | As for `timeline`.  Both documents' profiles are enforced. |
| `contract_extraction` | yes | `contract` | `ContractExtractor`: document details, then clauses and financial terms per chunk, then risks | Items below `confidence_threshold` get a warning in `contract.metadata.warnings`. |
| `risk_analysis` | yes, plus rules | `risks` | Keyword rules over extracted clauses, plus one model call over the first 20,000 characters | If the model call fails, only the rule results are returned (logged). |

Model-calling tasks need a provider: an `LLMProvider` instance, or a model
name (see [LLM providers](providers.md)).  There is no default, and a task
without one raises `ValueError`.

## Building a pipeline

```python
from contractex import LegalDoc
from contractex.core.legal_document import DocType
from contractex.tasks import TaskRegistry

text = open("examples/data/sample_nda.txt", encoding="utf-8").read()
doc = LegalDoc(doc_type=DocType.CONTRACT, full_text=text)

pipeline = TaskRegistry.default().build_pipeline(["pii_detection", "classification"])
result = pipeline.run(doc)

print(result.privacy_profile.sensitivity, result.privacy_profile.pii_entities_found)
print(result.extracted["cuad_labels"])
```

```text
confidential ['EMAIL_ADDRESS', 'PHONE_NUMBER']
['confidentiality', 'governing_law']
```

When `pii_detection` finds PII in a `public` document, it raises the
document's sensitivity to `confidential`.  That way the model-calling tasks
later in the pipeline redact their prompts.  To configure a task, pass
`task_kwargs={"<task_id>": {...}}` to `build_pipeline`.

`pipeline.run_async(doc)` runs the same tasks without blocking the event loop.

## Writing a task

Subclass `LegalTask`.  If the task calls a model, set `requires_llm = True`
and get the provider from `self.llm_for(doc)`, which enforces the document's
privacy profile on every call.  Pass every document whose text goes into the
prompt.

```python
from contractex.llm import LocalProvider
from contractex.tasks import LegalTask, TaskPipeline


class DefinedTermsTask(LegalTask):
    """Deterministic: list defined terms with the structure parser."""

    task_id = "defined_terms"
    requires_llm = False

    def run(self, doc, **kwargs):
        from contractex.structure import parse_structure

        doc.extracted["defined_terms"] = sorted(parse_structure(doc.full_text).defined_terms)
        return doc


class PlainEnglishTask(LegalTask):
    """Calls a model through the privacy router."""

    task_id = "plain_english"
    requires_llm = True

    def __init__(self, llm_provider):
        self._llm_provider = llm_provider

    def run(self, doc, **kwargs):
        prompt = f"Explain this agreement in two sentences:\n\n{doc.full_text[:4000]}"
        doc.extracted["plain_english"] = self.llm_for(doc).complete(prompt)
        return doc


pipeline = TaskPipeline([DefinedTermsTask(), PlainEnglishTask(LocalProvider(model="llama3.1:8b"))])
print(pipeline.run(doc).extracted["defined_terms"])
```

```text
['Agreement', 'Confidential Information', 'Harbourline', 'Kestrel', 'Purpose', 'Representatives']
```

To make a task available by name, register it with
`TaskRegistry.default().register(MyTask)`.
