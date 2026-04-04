import time
from config import generate_with_fallback

COST_PER_1K_INPUT = 0.000075
COST_PER_1K_OUTPUT = 0.0003


def instrumented_generate(prompt, agent_name):
    start = time.time()
    raw, i, o = generate_with_fallback(prompt, agent_name)
    elapsed = round(time.time() - start, 2)
    metrics = {"agent": agent_name, "wall_time_s": elapsed,
               "input_tokens": "N/A", "output_tokens": "N/A", "est_cost_usd": "N/A"}
    if i is not None and o is not None:
        metrics.update({
            "input_tokens": i,
            "output_tokens": o,
            "est_cost_usd": round((i / 1000) * COST_PER_1K_INPUT + (o / 1000) * COST_PER_1K_OUTPUT, 6),
        })
    return raw, metrics
