# config.py
# Single config for all LLM calls across the pipeline.
# Change PROVIDER and MODEL here — all agents pick it up automatically.
# Providers: "gemini" | "openai"

# Key design decision
# The design decision is: no single point of failure on the model call.
# The pipeline keeps running even when the primary model is unavailable.

import os
from dotenv import load_dotenv

load_dotenv()

from langfuse import Langfuse
from langfuse.types import TraceContext

langfuse = Langfuse(
    public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
    secret_key=os.environ["LANGFUSE_SECRET_KEY"],
    host=os.environ.get("LANGFUSE_BASE_URL", "https://cloud.langfuse.com"),
)

current_trace_id = None  # set by run.py before graph.invoke(); shared across all agent calls

PROVIDER = "gemini"
# PROVIDER = "openai"  # PAID!

# Gemini fallback chain — tried in order until one has quota
GEMINI_MODELS_FALLBACK = [
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
]

# OpenAI model to use
# Best price/performance for structured JSON tasks
# Handles all your agent prompts well
# Cheap enough that your entire project won't cost more than $2-3 total
OPENAI_MODEL = "gpt-4o-mini"  # cheap, capable — upgrade to gpt-4o if needed

# Upgrade to if gpt-4o-mini fails on compound risk reasoning: gpt-4o
# Stronger reasoning, ~15x more expensive; Only worth it if
# the dependency agent produces weak compound risks
# OPENAI_MODEL = "gpt-4o"

def generate_with_fallback(prompt: str, agent_name: str = "unknown") -> tuple[str, int | None, int | None]:
    trace_id = current_trace_id or Langfuse.create_trace_id()
    span = langfuse.start_observation(
        trace_context=TraceContext(trace_id=trace_id),
        name=agent_name,
        as_type="span",
    )
    result = _gemini(prompt) if PROVIDER == "gemini" else _openai(prompt)
    text, i, o = result
    span.update(usage_details={"input": i or 0, "output": o or 0})
    span.end()
    return text, i, o


def _gemini(prompt: str) -> tuple[str, int | None, int | None]:
    from google import genai
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    for model in GEMINI_MODELS_FALLBACK:
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt
            )
            print(f"[config] Used model: gemini/{model}")
            text = response.text.strip()
            try:
                i = response.usage_metadata.prompt_token_count
                o = response.usage_metadata.candidates_token_count
            except Exception:
                i, o = None, None
            return text, i, o
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                print(f"[config] gemini/{model} quota exhausted, trying next...")
                continue
            raise
    raise RuntimeError("All Gemini models exhausted — switch PROVIDER to openai")


def _openai(prompt: str) -> tuple[str, int | None, int | None]:
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}]
    )
    print(f"[config] Used model: openai/{OPENAI_MODEL}")
    text = response.choices[0].message.content.strip()
    try:
        i = response.usage.prompt_tokens
        o = response.usage.completion_tokens
    except Exception:
        i, o = None, None
    return text, i, o
