"""Subagent definitions and the lead-agent builder.

Orchestrator-worker pattern (Anthropic's multi-agent research system):
  - lead agent            -> plans, delegates, writes the pre-call brief.
  - competitor-scout      -> finds which competitors matter for the prospect.
  - prospect-researcher   -> researches the prospect company.
  - competitor-researcher -> deep-dives ONE competitor each, in parallel.
  - fact-checker          -> audits every sourced claim before it ships.
"""

from deepagents import create_deep_agent

from models import LEAD_MODEL, WORKER_MODEL
from prompts import (
    COMPETITOR_RESEARCHER_PROMPT,
    COMPETITOR_SCOUT_PROMPT,
    FACT_CHECKER_PROMPT,
    LEAD_AGENT_PROMPT,
    PROSPECT_RESEARCHER_PROMPT,
)
from tools import internet_search, log_tool_calls

competitor_scout_subagent = {
    "name": "competitor-scout",
    "description": (
        "Use FIRST when the competitors are not already given. Delegate the "
        "task of finding which competing products matter for this prospect. "
        "Your instruction MUST include: (1) what we sell and the vendor we "
        "resemble, (2) the prospect name, website and country if known, and "
        "(3) the `findings_file` path `/findings/scout.md`. It returns a ranked "
        "shortlist of competitors with homepage URLs and one-line reasons."
    ),
    "system_prompt": COMPETITOR_SCOUT_PROMPT,
    "tools": [internet_search],
    "model": WORKER_MODEL,
}

prospect_researcher_subagent = {
    "name": "prospect-researcher",
    "description": (
        "Research the PROSPECT company the AE is meeting: what they do, size, "
        "location, news and funding from the last 12 months, and what they use "
        "today in our category. Your instruction MUST include: (1) the prospect "
        "name plus website, country and size if known, (2) what we sell, and "
        "(3) the `findings_file` path `/findings/prospect.md`. Dispatch it in "
        "parallel with the competitor researchers."
    ),
    "system_prompt": PROSPECT_RESEARCHER_PROMPT,
    "tools": [internet_search],
    "model": WORKER_MODEL,
}

competitor_researcher_subagent = {
    "name": "competitor-researcher",
    "description": (
        "Delegate a deep-dive on ONE named competitor. Your task instruction "
        "MUST include: (1) the single competitor name (and homepage URL if "
        "known), (2) what we sell and who the prospect is, (3) the comparison "
        "dimensions: pricing, key features for this prospect, integrations, "
        "switching effort, (4) the other competitors so no two agents overlap, "
        "and (5) a unique `findings_file` path `/findings/<competitor-slug>.md`. "
        "It writes sourced findings to that file and returns a short synthesis "
        "plus the path. Dispatch several in parallel, one per competitor."
    ),
    "system_prompt": COMPETITOR_RESEARCHER_PROMPT,
    "tools": [internet_search],
    "model": WORKER_MODEL,
}

# Do not inherit the lead agent's search tool; audit the gathered findings only.
fact_checker_subagent = {
    "name": "fact-checker",
    "description": (
        "Use this AFTER drafting the brief and BEFORE returning it. Give it "
        "the `/notes.md` draft plus a pointer to the `/findings/` directory. It "
        "verifies every claim -- especially prices, funding figures, and what "
        "the prospect uses today -- is sourced, dated, and about the right "
        "company."
    ),
    "system_prompt": FACT_CHECKER_PROMPT,
    "tools": [],
    "model": WORKER_MODEL,
}


def build_agent(backend):
    """Wire the lead agent to its subagents and backend."""
    return create_deep_agent(
        model=LEAD_MODEL,
        tools=[internet_search],
        system_prompt=LEAD_AGENT_PROMPT,
        subagents=[
            competitor_scout_subagent,
            prospect_researcher_subagent,
            competitor_researcher_subagent,
            fact_checker_subagent,
        ],
        middleware=[log_tool_calls],
        backend=backend,
    )
