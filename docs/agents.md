# Agent Framework and LLM Runtime Documentation

This document describes the architecture, configuration, provider abstractions, retry runtime, and mathematical placeholder resolution implemented under **SPEC.md Section 5, 6, 7, 8, 21, and Milestone M5a**.

---

## 1. Architectural Overview

The agent framework provides a provider-agnostic, deterministic interface for executing LLM-based creative agents (such as the Curriculum Planner and Scriptwriter) alongside strict code-only verification stages (the Math Verifier).

```
+-------------------------------------------------------------+
|                     Topic & Inputs                          |
+-------------------------------------------------------------+
                              |
                              v
                  [Curriculum Planner Agent]
                 (curriculum_planner.md prompt)
                              |
                              v
                        [bible.json]  --> Stage: "plan" (status.json)
                              |
                              v
                    [Scriptwriter Agent]
                   (scriptwriter.md prompt)
                   (Includes claim specs)
                              |
                              v
                        [script.json]
                              |
                              v
                        [Gate G1 Script] <---+ (G1h digits, G1i number words)
                              |              |
                      Passes? |              | Auto-Regeneration Feedback Loop
                     +--------+--------+     | (up to 3 attempts with check IDs)
                     |                 |     |
                    Yes                No ---+
                     |
                     v
             Stage: "script" (status.json)
                     |
                     v
            [Math Verifier (Code Only)]
           (SymPy, checkers, safe_parse)
                     |
                     v
                [facts.json]
                     |
                     v
              [Gate G2 Math]
                     |
                     v
             Stage: "verify" (status.json)
```

### Core Design Principles
1. **Provider Agnostic:** Agents communicate through a unified `LLMProvider` interface. Model names and provider settings are configured externally in `config/llm.json` and are never hard-coded.
2. **Deterministic Math Verification:** LLMs NEVER supply computed mathematical values. The Scriptwriter proposes symbolic claim specifications; the Math Verifier evaluates and checks them deterministically with SymPy.
3. **Structured Pydantic Validation & Retries:** Every agent response is stripped of code fences, parsed as JSON, and validated against a Pydantic schema. Validation errors are fed back into the prompt for up to 3 automatic retries.
4. **Offline and Isolated Testing:** All tests run offline using `MockProvider`. No internet connection or live Ollama daemon is required during testing.
5. **Placeholder Number Discipline:** Narration text contains zero raw digits. Spoken numbers are referenced via `{{claim_id.field}}` placeholders that resolve to verified claims.

---

## 2. Configuration & Environment

### `config/llm.json`
Specifies execution parameters per agent role:
```json
{
  "roles": {
    "default": {
      "provider": "ollama",
      "model": "<fill-in>",
      "temperature": 0.7,
      "num_ctx": 4096,
      "timeout": 60.0,
      "max_retries": 3
    },
    "curriculum_planner": {
      "provider": "ollama",
      "model": "llama3.1:latest",
      "temperature": 0.3,
      "num_ctx": 4096,
      "timeout": 120.0,
      "max_retries": 3
    },
    "scriptwriter": {
      "provider": "ollama",
      "model": "llama3.1:latest",
      "temperature": 0.6,
      "num_ctx": 4096,
      "timeout": 120.0,
      "max_retries": 3
    }
  }
}
```
*Note: Real providers fail with a clear exception if their model remains `<fill-in>` or empty.*

### VRAM Budget and `num_ctx` Selection (6 GB VRAM)
- **Host GPU:** NVIDIA GeForce RTX 4050 Laptop GPU (6,141 MiB dedicated VRAM).
- **Model:** `llama3.1:latest` (Llama-3.1-8B-Instruct quantized to Q4_K_M).
- **Model Weight Footprint:** ~4.7–4.9 GB loaded in GPU memory.
- **KV Cache Sizing:**
  - Llama 3.1 8B uses 32 layers, 8 key-value heads, and head dimension 128 (GQA).
  - Each token requires: `2 * 32 layers * 8 KV heads * 128 dim * 2 bytes (FP16) = 131,072 bytes (128 KB)`.
  - At `num_ctx = 2048`: KV cache is `2048 * 128 KB = 256 MB`.
  - At `num_ctx = 4096`: KV cache is `4096 * 128 KB = 512 MB`.
  - At `num_ctx = 8192`: KV cache is `8192 * 128 KB = 1024 MB` (1.0 GB).
- **Justification for `num_ctx = 4096`:**
  - With 4.9 GB model weights + 512 MB KV cache + ~200 MB CUDA runtime overhead, total VRAM consumption is approximately **5.4 GB**, comfortably under the hard 6.0 GB ceiling.
  - Setting `num_ctx = 8192` pushes total allocation above 6.1 GB, causing Ollama to offload layers to system RAM or invoke memory paging, which collapses generation speed.
  - 4096 tokens provides ample room for the Curriculum Planner (~600 token prompt + ~1000 token output) and the Scriptwriter (~900 token prompt + ~400 token script output), ensuring complete zero-truncation execution at maximum GPU throughput.
- **Temperatures:**
  - `curriculum_planner`: **0.3** ensures disciplined, structured syllabus design and consistent pedagogical progression.
  - `scriptwriter`: **0.6** allows creative, natural spoken phrasing and metaphor while staying within mathematical constraints.

### Environment Variables (`.env`)
The lightweight `.env` parser (`agents/llm/env.py`) populates `os.environ` without overwriting existing system variables.
Supported variables:
- `GEMINI_API_KEY`: API key for Google Gemini (optional).
- `OLLAMA_HOST`: Base URL for Ollama daemon (defaults to `http://localhost:11434`).

*.env files and attempt logs (`agent_logs/`) are git-ignored. Secret keys are never committed.*

---

## 3. Provider Layer (`agents/llm/`)

### 1. `OllamaProvider` (`agents/llm/ollama.py`)
- Communicates directly with Ollama's HTTP endpoint (`http://localhost:11434/api/chat`).
- **Design Justification:** Plain HTTP (`urllib.request`) from the Python standard library was selected over the third-party `ollama` package to eliminate external wheel dependencies, prevent version pinning conflicts, and ensure transparent, fine-grained control over network timeouts and diagnostics.

### 2. `GeminiProvider` (`agents/llm/gemini.py`)
- Interfaces with Google's Gemini models.
- Uses lazy imports of `google.generativeai` inside `complete()`, allowing the repository to install and run offline without cloud packages installed.

### 3. `MockProvider` (`agents/llm/mock.py`)
- Provides deterministic, canned responses keyed by agent name.
- Supports `invalid_json_count` to simulate malformed outputs and thoroughly test agent retry loops.

### Adding a New Provider
To add a new provider:
1. Subclass `LLMProvider` in `agents/llm/<name>.py` and implement `complete(system, user, model, temperature, timeout, **kwargs) -> str`.
2. Register the provider in `create_provider()` inside `agents/llm/config.py`.
3. Add configuration presets for the provider in `config/llm.json`.

---

## 4. Structured Agent Runtime (`agents/runtime.py`)

### `run_agent` Execution Workflow
1. **Prompt Assembly:** Loads system prompt from `agents/<agent_name>.md` and formats user inputs.
2. **Provider Call:** Invokes `provider.complete(...)` with configured timeout and temperature.
3. **Fence Stripping:** Strips markdown code fences (```` ```json ```` and ```` ``` ````).
4. **Validation:** Parses JSON and validates against the Pydantic schema (e.g. `Bible`, `Script`).
5. **Retry Loop:** If parsing or validation fails, feeds the exact error back to the model for up to `max_retries` (default: 3).
6. **Logging:** Saves each attempt to `<log_dir>/<agent_name>_<attempt>.json` with system/user prompt, raw response, duration, and error.
7. **Failure:** Raises `AgentFailure` containing all attempt logs if retries are exhausted.

---

## 5. Mathematical Placeholders (`core/mathengine/placeholders.py`)

### Grammar
Placeholders follow the syntax:
```text
{{claim_id.field}}
```
For example:
- `{{c1.value}}`: Resolves to the verified numerical or symbolic value of claim `c1`.
- `{{c1.matrix}}`: Resolves to the matrix input of claim `c1`.

### Spoken-Form Translations (`Facts.spoken` / `to_spoken`)
Translates exact mathematical representations into spoken English for TTS synthesis and captioning:
- **Integers:** `2` -> `"two"`, `-5` -> `"minus five"`, `42` -> `"forty-two"`.
- **Fractions:** `1/2` -> `"one half"`, `-1/2` -> `"minus one half"`, `3/4` -> `"three quarters"`, `2/3` -> `"two thirds"`.
- **Powers:** `x**2` -> `"x squared"`, `x**3` -> `"x cubed"`, `x**4` -> `"x to the four"`, `x**n` -> `"x to the n"`.
- **Negatives:** Always prefixed with `"minus "`.
- **Strict Verification:** Calls to `Facts.spoken(key)` raise `UnverifiedClaimError` if the associated claim is not verified (`status != "verified"`). Unsupported mathematical shapes raise a clear `ValueError` without guessing.

### Pipeline Integration
- **TTS Narration:** `pipeline/narration.py` resolves placeholders in spoken mode before applying phonetic lexicon respellings.
- **Captions:** `pipeline/captions.py` resolves placeholders before verifying subtitle word alignments in `check_caption_text`.
- **Gate G1:**
  - `G1h_no_digits_in_narration`: Fails as a blocking error if literal digits (e.g. `2.7`) appear outside placeholders.
  - `G1i_number_words`: Emits a non-blocking warning listing line IDs when number words (e.g. "two", "three") appear outside placeholders, flagging them for human review at Gate G3.

---

## 6. Stages & Regeneration Loops (`agents/stages.py`)

1. **`plan_topic(topic_dir)`:** Runs Curriculum Planner to create `bible.json` and updates `status.json` (`plan: passed`).
2. **`write_script(chapter_dir)`:** Runs Scriptwriter to create `script.json`. Evaluates Gate G1 immediately; on failure, feeds failing check IDs back into the prompt for up to 3 automatic regenerations.
3. **`verify_math(chapter_dir)`:** Executes Math Verifier code, computes verified claims, saves `facts.json`, and updates Gate G2.
