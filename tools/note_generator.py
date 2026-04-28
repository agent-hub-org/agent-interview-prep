import logging
import os
import re
import uuid
from datetime import datetime, timezone

from langchain_core.tools import tool
from agent_sdk.utils.pdf import MarkdownPDFRenderer, slugify

logger = logging.getLogger("agent_interview_prep.tools.note_generator")

_BASE_URL = (os.getenv("BACKEND_URL") or os.getenv("PUBLIC_URL") or "").rstrip("/")
_pdf_renderer = MarkdownPDFRenderer()


def _generate_toc(content: str) -> str:
    toc_lines = []
    for line in content.split("\n"):
        if line.startswith("## "):
            heading = line[3:].strip()
            toc_lines.append(f"- [{heading}](#{slugify(heading)})")
        elif line.startswith("### "):
            heading = line[4:].strip()
            toc_lines.append(f"  - [{heading}](#{slugify(heading)})")
    return "\n".join(toc_lines)


@tool
async def generate_study_notes(title: str, content: str, format: str = "markdown", source_file_id: str | None = None) -> str:
    """Generate downloadable study notes from the provided content.

    Args:
        title: The title of the study notes (e.g., "System Design Interview Notes").
        content: The full markdown content of the study notes. Can be empty if source_file_id is provided.
        format: Output format - "markdown" or "pdf". Defaults to "markdown".
        source_file_id: Optional ID of a previously generated markdown file to use as the source content.
    """
    from database.mongo import MongoDB

    file_id = uuid.uuid4().hex
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    
    if source_file_id:
        result = await MongoDB.retrieve_file(source_file_id)
        if not result:
            return f"Error: source file {source_file_id} not found."
        data, meta = result
        try:
            retrieved_content = data.decode("utf-8")
        except Exception:
            return f"Error: source file is not valid text/markdown."
        title = title or "Study_Notes"
        slug = slugify(title, max_len=50)
        full_content = retrieved_content
        pdf_content = retrieved_content
    else:
        slug = slugify(title, max_len=50)
        # Add TOC to markdown content
        toc = _generate_toc(content)
        full_content = f"# {title}\n\n## Table of Contents\n{toc}\n\n---\n\n{content}"
        pdf_content = content

    # Determine filename
    if format == "pdf":
        filename = f"{timestamp}_{slug}.pdf"
    else:
        filename = f"{timestamp}_{slug}.md"

    try:
        if format == "pdf":
            file_bytes = _pdf_renderer.render(pdf_content, title)
        else:
            file_bytes = full_content.encode("utf-8")

        # Store in GridFS (persists across Railway deploys)
        await MongoDB.store_file(
            file_id=file_id,
            filename=filename,
            data=file_bytes,
            file_type="notes",
        )

        logger.info("Generated study notes: file_id='%s', format='%s', size=%d bytes",
                     file_id, format, len(file_bytes))

        return (
            f"Study notes generated successfully!\n\n"
            f"**Title:** {title}\n"
            f"**Format:** {format.upper()}\n"
            f"**Download:** [Download: {title}]({_BASE_URL}/download/{file_id})"
        )

    except Exception as e:
        logger.error("Failed to generate study notes: %s", e)
        return (
            f"Error generating study notes ({format}): {e}. "
            "Do NOT retry with the same format. "
            "If format was 'pdf', call this tool again with format='markdown' instead — "
            "markdown supports all Unicode and math notation without restrictions."
        )
