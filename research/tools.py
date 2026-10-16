"""Web search tool (the workers' primary tool) and a tool-call logger.

When the ``AGENT_TRACE_DIR`` env var points at a directory, every
``internet_search`` call (with its query and a compact result summary) is
appended as one JSONL line to ``<AGENT_TRACE_DIR>/tool_calls.jsonl`` for
inspection after the run.
Persistence lives on the tool function itself (not on the middleware) because
subagent tool calls do not pass through the parent agent's middleware.
"""

import json
import logging
import os
import time
from typing import Literal

from langchain.agents.middleware import wrap_tool_call
from tavily import TavilyClient

from search_policy import excluded_search_domains

logger = logging.getLogger(__name__)


SEARCH_ATTEMPTS = 2


def _tavily_client():
    """Build the client lazily after OpenShell has injected its placeholder."""
    return TavilyClient(api_key=os.environ["TAVILY_API_KEY"])


def internet_search(
    query: str,
    max_results: int = 5,
    topic: Literal["general", "news", "finance"] = "general",
    include_raw_content: bool = False,
):
    """Run a web search and return results (title, url, content snippet).

    Use specific, narrow queries. For pricing or funding, prefer the
    competitor's own domain or `topic="finance"`.
    """
    if not 1 <= max_results <= 10:
        raise ValueError("max_results must be between 1 and 10")

    excluded_domains = excluded_search_domains()
    # One failed search must not end the whole run: retry once, then hand the
    # error to the model so it can carry on and report the gap.
    failure = None
    for attempt in range(SEARCH_ATTEMPTS):
        try:
            response = _tavily_client().search(
                query,
                max_results=max_results,
                include_raw_content=include_raw_content,
                topic=topic,
                exclude_domains=excluded_domains,
            )
            break
        except Exception as error:  # network, TLS, rate limit, bad response
            failure = error
            logger.warning("Search failed (attempt %d): %s", attempt + 1, error)
            if attempt + 1 < SEARCH_ATTEMPTS:
                time.sleep(2)
    else:
        response = {
            "query": query,
            "error": f"Search failed: {type(failure).__name__}. Retry later or "
                     "note this as a gap. Do not guess the answer.",
            "results": [],
        }
    # Subagent tool calls do not pass through the parent's middleware, so
    # persist searches at the function level to ensure they always land in the
    # trace, regardless of which agent invoked them.
    _persist_search_call(query, max_results, topic, excluded_domains, response)
    return response


def _persist_search_call(query, max_results, topic, excluded_domains, response):
    trace_dir = os.environ.get("AGENT_TRACE_DIR")
    if not trace_dir:
        return
    entry = {
        "tool": "internet_search",
        "args": {
            "query": query,
            "max_results": max_results,
            "topic": topic,
            "excluded_domains": excluded_domains,
        },
        "response": _summarize_for_trace("internet_search", response),
    }
    with open(os.path.join(trace_dir, "tool_calls.jsonl"), "a") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def _summarize_for_trace(tool_name, response):
    """Return a JSON-safe summary of a tool response for the trace log."""
    payload = getattr(response, "content", response)

    if tool_name == "internet_search" and isinstance(payload, dict):
        return {
            "query": payload.get("query"),
            **({"error": payload["error"]} if payload.get("error") else {}),
            "results": [
                {
                    "title": r.get("title"),
                    "url": r.get("url"),
                    "score": r.get("score"),
                    "content": (r.get("content") or "")[:400],
                }
                for r in payload.get("results", [])
            ],
        }

    if isinstance(payload, (dict, list)):
        try:
            s = json.dumps(payload, default=str)
        except TypeError:
            s = str(payload)
    else:
        s = str(payload)
    return s if len(s) <= 800 else s[:799] + "…"


@wrap_tool_call
def log_tool_calls(request, handler):
    tool_call = getattr(request, "tool_call", None)
    if isinstance(tool_call, dict):
        tool_name = tool_call.get("name", "tool")
        tool_args = tool_call.get("args")
    else:
        tool_name = getattr(request, "name", "tool")
        tool_args = getattr(request, "args", None)

    if tool_args:
        summary = str(tool_args)
        if len(summary) > 200:
            summary = summary[:199] + "…"
        logger.info("→ %s(%s)", tool_name, summary)
    else:
        logger.info("→ %s", tool_name)
    return handler(request)
