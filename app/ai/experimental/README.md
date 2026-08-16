# Experimental

Written, kept, and **not wired to any route**. Nothing in `app/` imports this package.

| Module | What it is | Why it is here |
|---|---|---|
| `concept_chain.py` | A 3-stage LCEL pipeline: extract concepts → enrich each → format a Markdown report. | Was `app/ai/chain.py`. A worked example of multi-stage LCEL with `JsonOutputParser`; no endpoint ever called it. |
| `image_gen.py` | Gemini image generation via LiteLLM, returning a PIL image. | Was `app/ai/image.py`. Has a `__main__` block, so it runs standalone. |

## Before wiring either one up

- **`image_gen.py` will not import as-is.** It needs `litellm`, `Pillow` and `requests`;
  only `requests` is in `requirements.txt`. This is deliberate — they are heavy
  dependencies for code no request path reaches. Add them at the point you add the
  endpoint, not before.
- Both call the LLM providers directly instead of going through
  `app/ai/chat/models.py`, so they do not get the shared client reuse or the
  Groq→Gemini fallback that the live chat path has.
- Neither is traced. There is no `@traceable` on either, so they will not appear in
  LangSmith next to the rest of a request.
