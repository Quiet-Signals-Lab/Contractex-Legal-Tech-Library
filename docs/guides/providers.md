# LLM providers

Contractex never chooses a provider or a model for you.  Every component that
calls a model needs one passed in explicitly.  The core install includes no
vendor SDK: install the extra for the provider you use.

| Provider | Install | Class | Needs |
|---|---|---|---|
| Ollama (runs locally) | `pip install "contractex[ollama]"` | `LocalProvider` | [Ollama](https://ollama.com) running, the model pulled (`ollama pull <model>`); `OLLAMA_HOST` if not `http://localhost:11434` |
| OpenAI | `pip install "contractex[openai]"` | `OpenAIProvider` | `OPENAI_API_KEY` |
| Anthropic | `pip install "contractex[anthropic]"` | `AnthropicProvider` | `ANTHROPIC_API_KEY` |
| Google | `pip install "contractex[google]"` | `GoogleProvider` | `GOOGLE_API_KEY` |
| LangChain | `pip install "contractex[langchain]"` | `LangChainProvider` | a LangChain chat model instance |

Only `LocalProvider` is treated as local by the [privacy router](privacy.md),
so it is the only provider allowed for `restricted` documents.

## Model names

These docs do not list cloud model identifiers, because they change.  Use the
identifier from your vendor's current list:
[OpenAI](https://platform.openai.com/docs/models),
[Anthropic](https://docs.anthropic.com/en/docs/about-claude/models),
[Google](https://ai.google.dev/gemini-api/docs/models),
[Ollama](https://ollama.com/library).  The only identifier used in these docs
is the Ollama tag `llama3.1:8b`, in the local examples.

```python
from contractex.llm import AnthropicProvider, LocalProvider, OpenAIProvider

local = LocalProvider(model="llama3.1:8b")
openai = OpenAIProvider(model="your-openai-model-id")
anthropic = AnthropicProvider(model="your-anthropic-model-id")
```

Anywhere a provider is accepted, you can pass a model name instead.  A name
beginning `gpt-` creates an `OpenAIProvider`, `claude-` an
`AnthropicProvider`, and anything else a `LocalProvider` for that Ollama model.
A vendor name on its own is rejected rather than mapped to a model the library
picks:

```python
from contractex import ContractExtractor

try:
    ContractExtractor(llm_provider_name="openai")
except ValueError as exc:
    print(exc)
```

```text
'openai' does not name a model.  Pass a full model name such as 'gpt-...' or 'claude-...', or an LLMProvider instance.
```

## Writing a provider

Subclass `LLMProvider` and implement `complete`, `extract_structured`,
`estimate_cost`, `count_tokens`, `context_window` and `model`.  The
[privacy guide](privacy.md#seeing-what-leaves-the-process) has a complete
example, a provider that prints its prompts, which is also useful for testing.

## Known issues

- **Anthropic:** the extra is pinned to `anthropic<1.0`.  Version 1.0 of the
  SDK removed the `temperature` parameter that `AnthropicProvider` passes on
  every call.
- **Google:** `GoogleProvider` uses the `google-genai` SDK and falls back to
  the deprecated `google-generativeai` if that is what is installed.  Neither
  path is tested against the live API in this repository.
- **Cost estimates:** `estimate_cost()` uses price tables built into each
  provider class, which date from 2024.  Treat them as rough and check your
  vendor's pricing.
- **Determinism:** model output varies between runs, even at temperature 0.
  Measure quality with the [evaluation harness](evaluation.md) rather than
  assuming it.
