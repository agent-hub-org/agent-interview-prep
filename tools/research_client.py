import logging
import os

import httpx
from langchain_core.tools import tool

logger = logging.getLogger("agent_interview_prep.tools.research_client")

RESEARCH_AGENT_URL = os.getenv("RESEARCH_AGENT_URL", "http://localhost:9002")


@tool
async def research_topic(query: str) -> str:
    """Delegate a research query to the Research Agent.

    ONLY use this for topics that are niche, recent (post-2023), or require academic paper
    summaries. Do NOT call it for well-established concepts (e.g., dropout, backpropagation,
    attention mechanisms, transformers, common algorithms, standard data structures, classic
    system design patterns) — answer those directly from your own knowledge.
    Call this tool at most ONCE per user turn.

    Args:
        query: The research query to send to the research agent.
    """
    logger.info("Delegating research query to %s: '%s'", RESEARCH_AGENT_URL, query[:100])

    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                f"{RESEARCH_AGENT_URL}/ask",
                json={"query": query},
            )
            response.raise_for_status()
            data = response.json()
            result = data.get("response", "")
            logger.info("Research agent returned %d chars", len(result))
            return result

    except httpx.TimeoutException:
        logger.error("Research agent timed out for query: '%s'", query[:100])
        return "The research agent timed out. Please try a more specific query."
    except httpx.HTTPStatusError as e:
        logger.error("Research agent returned %d: %s", e.response.status_code, e)
        return f"Research agent error (HTTP {e.response.status_code}). It may be unavailable."
    except httpx.ConnectError:
        logger.error("Cannot connect to research agent at %s", RESEARCH_AGENT_URL)
        return (
            "Cannot connect to the research agent. "
            "Please ensure it is running and try again."
        )
