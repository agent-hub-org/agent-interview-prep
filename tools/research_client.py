import logging
import os

import httpx
from langchain_core.tools import tool

logger = logging.getLogger("agent_interview_prep.tools.research_client")

RESEARCH_AGENT_URL = os.getenv("RESEARCH_AGENT_URL", "http://localhost:9002")


@tool
async def research_topic(query: str) -> str:
    """Delegate a deep research query to the Research Agent. Use this when the user needs
    in-depth technical explanations, academic paper summaries, or comprehensive topic overviews
    that go beyond your knowledge.

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
