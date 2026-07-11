# Handwritten bore-log vision provider (Phase 1.5, W6)

Runtime-configured vision-provider layer behind the seam in `truelinev2/extract/handwritten_borelog.py`.
A page with no usable text layer (a scanned/photographed PDF page, or any image upload) is resolved by a
**deployment-selected vision provider**, loaded by **dotted module path** at runtime. **All flags default
OFF/unset; OFF is byte-identical.** No vendor/model literal lives in the seam, in `config.py`, or anywhere
outside `truelinev2/extract/vision_providers/anthropic_messages.py` (the ONE file where the vendor name
"anthropic" is allowed to appear).

## Config matrix

| Env var | Read by | Meaning | Default |
|---|---|---|---|
| `TL2_HANDWRITTEN_BORELOG_EXTRACTION_OPTIN` | `config.py` | Enables the Phase-1 handwritten extraction tier at all (image uploads, fan-out, review/source routes). | unset (off) |
| `TL2_HANDWRITTEN_BORELOG_TIMEOUT_SECONDS` | `config.py` | Hard per-page timeout (seconds) around one provider call. | `90` |
| `TL2_HANDWRITTEN_BORELOG_PROVIDER` | `config.py` | **Dotted module path** to a provider module (e.g. `truelinev2.extract.vision_providers.anthropic_messages`). `extract/handwritten_borelog.py`'s factory imports it lazily and calls its `build_provider(config)`. | unset (no provider — every vision-needing page refuses honestly) |
| `TL2_HANDWRITTEN_VISION_MODEL` | `anthropic_messages.py` (the adapter itself, via `config.get_env`) | Anthropic model id for the vision call. **No default/hardcoded model literal anywhere in this repo** — unset means the adapter cannot build a provider. | unset |
| `TL2_HANDWRITTEN_FAKE_FIXTURES` | `fake.py` (the fixture provider itself) | Directory of pre-built `HandwrittenPageExtraction` JSON fixtures, keyed `<sha256>-p<page_index>.json`. Tests/proofs only. | unset |
| *(deployment config, not a `TL2_*` flag)* `ANTHROPIC_API_KEY` (or the SDK's other standard credential sources) | the `anthropic` SDK itself | API key. **Never read, logged, or touched by any code in this repo** — the adapter constructs `anthropic.Anthropic()` with no key argument and lets the SDK resolve credentials from its own standard environment/profile chain. | unset |

`TL2_HANDWRITTEN_BORELOG_PROVIDER` replaces what was, before this wave, an always-empty in-process
provider registry. The env var's *name* is unchanged; its *value* now means a dotted module path rather
than an opaque registry key.

## Fail-closed behavior

Every failure mode maps to one of the seam's existing/new named page refusals — never a 500, never an
invented reading:

| Situation | Refusal code | Reason content |
|---|---|---|
| `TL2_HANDWRITTEN_BORELOG_PROVIDER` unset | `HANDWRITTEN_VISION_PROVIDER_NOT_CONFIGURED` | generic "no vision provider is configured…" |
| Provider module import fails, has no/non-callable `build_provider`, or `build_provider` raises (including a provider's own `ProviderUnavailable`, e.g. missing SDK or missing `TL2_HANDWRITTEN_VISION_MODEL`) | `HANDWRITTEN_VISION_PROVIDER_NOT_CONFIGURED` | sanitized: module **tail** + exception **class name** only — never a message, path, or traceback |
| Provider call still running past `TL2_HANDWRITTEN_BORELOG_TIMEOUT_SECONDS` | `HANDWRITTEN_EXTRACTION_TIMEOUT` | fixed message naming the timeout |
| Provider callable raises `ProviderOutputInvalid` (malformed/refused model response, missing fixture, …), its returned dict fails `validate_page_extraction`, or its claimed `source` sha256/upload_id/page_index **disagrees** with the real page it was given (a spoof attempt) | `HANDWRITTEN_PROVIDER_OUTPUT_INVALID` | ALWAYS one of two FIXED literals — `"provider returned output that failed validation"` or, for the identity-mismatch case, `"provider output did not match the requested page"` — **never** the raised exception's own message, which is untrusted provider-authored text a provider could poison (a URL, a token-shaped string, …) |
| Provider callable raises anything else (network error, SDK auth/permission error, a bare `RuntimeError`, …) | `HANDWRITTEN_PROVIDER_ERROR` *(new this wave)* | the exception's **class name only** — e.g. `"the vision provider raised AuthenticationError"` — **never** the exception message, which may embed request/URL/header/key-adjacent details |

The API key itself, and any raised exception's own message, is never part of any refusal, log line, or
result this repo constructs — not even a `ProviderOutputInvalid` a provider module raised deliberately.
Only the two fixed literals above (or, for `HANDWRITTEN_PROVIDER_ERROR`, the exception's class name) ever
leave `extract/handwritten_borelog.py`'s `_run_provider_with_timeout`.

## Trust boundary — a provider's own claims are never trusted

A provider callable's returned `source`/`method`/`extractor` fields are **never trusted**. The seam
FORCE-ASSIGNS all three from its own already-known-good values after every provider call:

- `source` — this page's real `upload_id`/`sha256`/`file_name`/`page_index`/`page_count`, computed by
  `extract_handwritten` itself from the uploaded bytes, never from the provider's response.
- `method` — always `VISION_OCR` (this is the vision-provider seam; a provider cannot claim otherwise).
- `extractor` — always the resolved provider's module tail (or the test-injection name), never a value
  the provider's own output chose.

A provider that simply **omits** `source` (or omits its keys) is not spoofing anything — the seam fills
identity in silently, no refusal. A provider that **claims** a `source` whose `sha256`, `upload_id`, or
`page_index` **disagrees** with the real value is treated as a spoof attempt and refuses LOUDLY
(`HANDWRITTEN_PROVIDER_OUTPUT_INVALID`, fixed reason `"provider output did not match the requested page"`)
rather than being silently corrected — a disagreement must be visible, never quietly patched over.

## Retry policy and timeout budgeting (Anthropic adapter only)

`anthropic_messages.py` retries a single page's Messages API call — only on 429 (rate limit), 5xx (server
error), or a connection/timeout error — with a short jittered backoff between attempts. A 4xx auth/
permission error, or any other non-retryable failure, is **never** retried; it propagates on the first
attempt and the seam reduces it to `HANDWRITTEN_PROVIDER_ERROR` (class name only).

**The seam's own per-page timeout (`TL2_HANDWRITTEN_BORELOG_TIMEOUT_SECONDS`) is a `threading.Thread.
join(timeout)` around the whole provider call — on timeout it merely ABANDONS the still-running daemon
thread (Python has no safe way to forcibly kill a thread) and reports `HANDWRITTEN_EXTRACTION_TIMEOUT`;
it does NOT stop the underlying network call.** To actually bound the real work, the adapter derives an
explicit SDK-level request timeout from `config.timeout_seconds` — the seam timeout minus a small margin,
floored at 5s — and passes it to the Anthropic client (`timeout=` kwarg) via its `client_factory`. That
SDK-level timeout, not the seam's join(), is what actually terminates a hung request. Because a single
attempt can already take up to that derived timeout, the number of retry attempts is **recomputed DOWN**
(never above the desired ceiling, never below 1) so the worst case — every attempt using the full
per-attempt timeout — still fits inside the seam's own overall budget; at the default 90s seam timeout
this leaves room for only **1** attempt (retries need a larger `TL2_HANDWRITTEN_BORELOG_TIMEOUT_SECONDS`
to have headroom). The adapter constructs its own `anthropic.Anthropic(max_retries=0, timeout=…)` client,
so this adapter-level retry loop is the ONLY retry logic in play (no doubled retries from the SDK's own
default client-level retry behavior).

## Observability

One `INFO` log line per provider page call, logger `truelinev2.extract.vision_providers`:

```
vision provider call: provider=<module tail> page_index=<n> outcome=<EXTRACTED|refusal code> duration_ms=<n> attempts=<n>
```

`attempts` defaults to `1` (a provider that never reports otherwise made exactly one call); the Anthropic
adapter reports the real count on every retry. The log line **never** includes the page image bytes, the
API key, or any other env/secret value — only the provider module's tail, the page index, the outcome
code, timing, and attempt count. `truelinev2/tests/test_vision_providers.py` asserts this with a caplog
scan (a deliberately-set fake secret env value must never appear in any captured log record).

## Staging activation

Enabling a real vision provider on staging is a **deployment config change only** — no code change, no
redeploy of a new image needed beyond what already ships this wave. The env vars above (`TL2_HANDWRITTEN_BORELOG_EXTRACTION_OPTIN`,
`TL2_HANDWRITTEN_BORELOG_PROVIDER`, `TL2_HANDWRITTEN_VISION_MODEL`, and the SDK's own `ANTHROPIC_API_KEY`)
live in the gitignored staging supervisor's `Start-Backend` block
(`data/outputs/truelinev2/staging_smoke/ops/staging-supervisor.ps1`) alongside the other live `TL2_*`
flags. **This doc does not edit that file** — activation is an owner-gated, out-of-repo config action; see
`wiki/START_HERE_TRUELINE_V2.md` / the staging supervisor's own `-Status` output for the current live flag
set before flipping any of these in a real environment. Until a provider is actually configured there,
staging behavior is unchanged: every vision-needing page still refuses honestly with
`HANDWRITTEN_VISION_PROVIDER_NOT_CONFIGURED`.

## Provider module contract

A provider module (loaded by dotted path) exposes exactly one function:

```python
def build_provider(config) -> Callable[[bytes, dict], dict]:
    ...
```

`config` is `truelinev2.extract.handwritten_borelog.ProviderConfig` — a small read-only view carrying
`timeout_seconds` (float) and `get_env` (bound `os.environ.get`), so a provider module reads **its own**
env vars directly and this seam never names a third-party env var. `build_provider` may raise
`truelinev2.extract.vision_providers.ProviderUnavailable` when it cannot construct a callable at all
(missing SDK, missing a required env var); any other exception it raises is treated the same way.

The returned callable's contract is `(page_png_bytes: bytes, context: dict) -> HandwrittenPageExtraction`.
`context` carries `upload_id`, `file_name`, `page_index`, `page_count`, `sha256`, and an optional
`report_attempts(int)` callable a provider MAY call once per internal attempt (observability only — never
affects control flow). The returned dict is re-validated by the seam via `validate_page_extraction`
regardless of what the provider returns. A provider callable may raise
`truelinev2.extract.vision_providers.ProviderOutputInvalid` to signal an honest per-page refusal (never
invent a reading); any other raised exception becomes `HANDWRITTEN_PROVIDER_ERROR` (class name only).

Two provider modules ship in this repo:

- `truelinev2/extract/vision_providers/fake.py` — deterministic, fixture-driven, for tests/proofs only.
- `truelinev2/extract/vision_providers/anthropic_messages.py` — the real Anthropic Messages API adapter
  (the vendor isolation boundary — see its own module docstring for the full request/response shape).
