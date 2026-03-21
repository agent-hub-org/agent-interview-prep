import logging

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore

from .agent_card import INTERVIEW_PREP_AGENT_CARD
from .executor import InterviewPrepExecutor

logger = logging.getLogger("agent_interview_prep.a2a_server")


def create_a2a_app() -> A2AStarletteApplication:
    """Build the A2A Starlette application for the interview prep agent."""
    task_store = InMemoryTaskStore()
    executor = InterviewPrepExecutor()
    request_handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=task_store,
    )
    a2a_app = A2AStarletteApplication(
        agent_card=INTERVIEW_PREP_AGENT_CARD,
        http_handler=request_handler,
    )
    logger.info("A2A application created for Interview Prep Agent")
    return a2a_app
