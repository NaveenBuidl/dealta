# Nodes = the agents (what runs).
# Edges = the order (what runs after what).
# A node is a function. An edge is an arrow saying "when this finishes, run that next."
# Why this structure instead of just calling the functions in sequence in a for loop?
# LangGraph manages state passing between nodes automatically. 
# If you just called functions in a for loop, 
# you'd have to manually pass the state object from one function to the next and 
# track what's been written. 
# LangGraph enforces that every node receives the full state and returns the full state. 
# Nothing gets lost or overwritten accidentally.
# the primary value is guaranteed state integrity between steps.
# Imagine you're passing a baton in a relay race.
# For-loop version: each runner has to remember to grab the baton from the previous runner, 
# hold it correctly, and hand it off properly. If one runner forgets, 
# the baton drops and nobody notices until the race is over.
# LangGraph version: there's a race official standing at every exchange point 
# whose only job is to make sure the baton is passed correctly every single time. 
# Runners just run. The official handles the handoff.
# The "baton" is the state object. The "race official" is LangGraph's StateGraph.
# In practice: if you forgot to include a field in a return statement in a for-loop setup, 
# that field would silently disappear from state. 
# The next agent would get an incomplete picture and you'd have no idea why. 
# LangGraph catches this at the structural level.
# Why is DEALta multi-agent instead of one big prompt?
# when something breaks, you know exactly where to look. 
# Plus separation of  concerns for detection, routing, policy checking and compound risk flagging.
# Each agent has a narrow job, a clear input, a clear output, and its own eval. 
# You can score change detection at 100% and routing at 89% independently. If they were merged, a routing error would look like a detection error and you'd have no way to isolate it.
# The answer for interviews: single responsibility plus independent evaluability. 
# Failures are traceable to a specific agent, not buried in a 2000-token prompt.


from langgraph.graph import StateGraph, START, END
from state.schema import DEALtaState
from agents import change_detection, routing, policy_check, dependency, invalidation, decision_pack


def build_graph():
    builder = StateGraph(DEALtaState)

    builder.add_node("change_detection", change_detection.run)
    builder.add_node("invalidation", invalidation.run)
    builder.add_node("routing", routing.run)
    builder.add_node("policy_check", policy_check.run)
    builder.add_node("dependency_check", dependency.run)
    builder.add_node("decision_pack", decision_pack.run)

    builder.add_edge(START, "change_detection")
    builder.add_edge("change_detection", "invalidation")
    builder.add_edge("invalidation", "routing")
    builder.add_edge("routing", "policy_check")
    builder.add_edge("policy_check", "dependency_check")
    builder.add_edge("dependency_check", "decision_pack")
    builder.add_edge("decision_pack", END)

    return builder.compile()

def build_graph_skip_detection():
    builder = StateGraph(DEALtaState)

    builder.add_node("invalidation", invalidation.run)
    builder.add_node("routing", routing.run)
    builder.add_node("policy_check", policy_check.run)
    builder.add_node("dependency_check", dependency.run)
    builder.add_node("decision_pack", decision_pack.run)

    builder.add_edge(START, "invalidation")
    builder.add_edge("invalidation", "routing")
    builder.add_edge("routing", "policy_check")
    builder.add_edge("policy_check", "dependency_check")
    builder.add_edge("dependency_check", "decision_pack")
    builder.add_edge("decision_pack", END)

    return builder.compile()