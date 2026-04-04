# LLM-as-Judge eval — narrative faithfulness check

import json
import os
import sys

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

PIPELINE_OUTPUT = "outputs/pipeline_output_nexus_staylink_001_v3.json"
JUDGE_MODEL = "gpt-4o-mini"
GENERATOR_MODEL = "gemini"


def load_structured_findings(data: dict) -> dict:
    detected_changes = [
        c for c in data.get("detected_changes", [])
        if c.get("materiality_level") in ("critical", "high")
    ]
    policy_flags = data.get("policy_flags", [])
    compound_risks = data.get("compound_risks", [])
    sign_offs = [s for s in data.get("sign_offs", []) if s.get("invalidated") is True]

    return {
        "detected_changes": detected_changes,
        "policy_flags": policy_flags,
        "compound_risks": compound_risks,
        "invalidated_sign_offs": sign_offs,
    }


def main():
    with open(PIPELINE_OUTPUT) as f:
        data = json.load(f)

    summary_narrative = data["decision_pack"]["summary_narrative"]
    structured_findings = load_structured_findings(data)

    structured_findings_json = json.dumps(structured_findings, indent=2)

    judge_prompt = f"""You are evaluating a generated narrative summary against the structured findings it is supposed to reflect.

STRUCTURED FINDINGS:
{structured_findings_json}

GENERATED NARRATIVE:
{summary_narrative}

Judge criterion: Does the narrative accurately reflect the structured findings — detected changes, policy flags, compound risks, sign-off invalidations — without adding claims not present in the data?

Respond in exactly this format:
Narrative faithfulness: PASS
Reasoning: [one sentence]

Or:
Narrative faithfulness: FAIL
Reasoning: [one sentence naming the specific unfaithful claim]"""

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    # Judge call — OpenAI gpt-4o-mini evaluates Gemini-generated narrative
    response = client.chat.completions.create(
        model=JUDGE_MODEL,
        messages=[{"role": "user", "content": judge_prompt}],
    )

    result = response.choices[0].message.content.strip()
    print(result)
    print(f"\nJudge model: openai/{JUDGE_MODEL}")
    print(f"Generator model: {GENERATOR_MODEL}")


if __name__ == "__main__":
    main()
