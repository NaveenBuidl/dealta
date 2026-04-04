# test_agent.py
# Test a single agent in isolation. 1 API call, not 5.
# Usage: python test_agent.py <agent_name>
# Example: python test_agent.py invalidation

import sys
import json
from datetime import datetime, timezone
from state.schema import DEALtaState

def load(path):
    with open(path) as f:
        return f.read()

# Load a saved pipeline output as the base state
with open("pipeline_output.json") as f:
    base_state = json.load(f)

agent_name = sys.argv[1] if len(sys.argv) > 1 else None

if agent_name == "invalidation":
    from agents import invalidation
    result = invalidation.run(base_state)
    print(json.dumps(result.get("sign_offs", []), indent=2))

elif agent_name == "dependency":
    from agents import dependency
    result = dependency.run(base_state)
    print(json.dumps(result.get("compound_risks", []), indent=2))

# Add more agents as needed
else:
    print(f"Unknown agent: {agent_name}")
    print("Available: invalidation, dependency")