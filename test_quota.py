# test_quota.py
# Run at the start of each session to check which models have quota available.
# Usage: python test_quota.py

import os
from dotenv import load_dotenv
from google import genai

load_dotenv()
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

# Only valid API model strings — confirmed via 404 testing
MODELS_TO_TEST = [
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
]

print("\n=== GEMINI QUOTA CHECK ===\n")

available = []
exhausted = []

for model in MODELS_TO_TEST:
    try:
        response = client.models.generate_content(
            model=model,
            contents="Reply with OK"
        )
        print(f"[OK]    {model}")
        available.append(model)
    except Exception as e:
        if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
            print(f"[429]   {model} — quota exhausted")
            exhausted.append(model)
        else:
            print(f"[ERR]   {model} — {str(e)[:80]}")

print("\n=== SUMMARY ===")
print(f"Available now: {available if available else 'none'}")
print(f"Exhausted:     {exhausted if exhausted else 'none'}")

if available:
    print(f"\nPipeline will use: {available[0]} (first available in fallback order)")
else:
    print("\nNo models available — wait for quota reset or switch to OpenAI")

print()