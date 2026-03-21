import logging
import os
import re

from langchain_core.tools import tool

logger = logging.getLogger("agent_interview_prep.tools.resume_parser")

# Common resume section headings
SECTION_KEYWORDS = {
    "education": ["education", "academic", "degree", "university", "college"],
    "experience": ["experience", "employment", "work history", "professional experience"],
    "skills": ["skills", "technical skills", "technologies", "competencies", "proficiencies"],
    "projects": ["projects", "personal projects", "academic projects"],
    "certifications": ["certifications", "certificates", "licenses"],
    "summary": ["summary", "objective", "profile", "about me", "overview"],
    "publications": ["publications", "papers", "research"],
    "awards": ["awards", "honors", "achievements"],
}


def _extract_text_from_pdf(file_path: str) -> str:
    """Extract text from a PDF file using pymupdf."""
    import pymupdf

    doc = pymupdf.open(file_path)
    text_parts = []
    for page in doc:
        text_parts.append(page.get_text())
    doc.close()
    return "\n".join(text_parts)


def _extract_text_from_docx(file_path: str) -> str:
    """Extract text from a DOCX file using python-docx."""
    from docx import Document

    doc = Document(file_path)
    return "\n".join(para.text for para in doc.paragraphs if para.text.strip())


def _detect_sections(text: str) -> dict[str, str]:
    """Attempt to detect resume sections by keyword matching on headings."""
    lines = text.split("\n")
    sections: dict[str, list[str]] = {}
    current_section = "other"
    sections[current_section] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            sections.setdefault(current_section, []).append("")
            continue

        # Check if this line looks like a section heading
        lower = stripped.lower()
        matched_section = None
        for section_name, keywords in SECTION_KEYWORDS.items():
            if any(lower == kw or lower.startswith(kw + ":") or lower.startswith(kw + " ") for kw in keywords):
                # Likely a heading if it's short
                if len(stripped) < 60:
                    matched_section = section_name
                    break

        if matched_section:
            current_section = matched_section
            sections.setdefault(current_section, [])
        else:
            sections.setdefault(current_section, []).append(stripped)

    return {k: "\n".join(v).strip() for k, v in sections.items() if "\n".join(v).strip()}


def _extract_skills(text: str) -> list[str]:
    """Extract likely skill keywords from the resume text."""
    # Common tech skills pattern matching
    tech_patterns = [
        r'\b(?:Python|Java|JavaScript|TypeScript|C\+\+|C#|Go|Rust|Ruby|Swift|Kotlin|Scala|R|MATLAB)\b',
        r'\b(?:React|Angular|Vue|Node\.js|Django|Flask|FastAPI|Spring|Express|Next\.js)\b',
        r'\b(?:AWS|GCP|Azure|Docker|Kubernetes|Terraform|Jenkins|CI/CD)\b',
        r'\b(?:PostgreSQL|MongoDB|MySQL|Redis|Elasticsearch|DynamoDB|Cassandra)\b',
        r'\b(?:TensorFlow|PyTorch|Scikit-learn|Pandas|NumPy|Keras|Hugging Face)\b',
        r'\b(?:Machine Learning|Deep Learning|NLP|Computer Vision|LLM|RAG|MLOps)\b',
        r'\b(?:SQL|REST|GraphQL|gRPC|Kafka|RabbitMQ|Spark|Hadoop|Airflow)\b',
        r'\b(?:Git|Linux|Agile|Scrum|Microservices|System Design|Data Structures)\b',
    ]

    skills = set()
    for pattern in tech_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        skills.update(m.strip() for m in matches)

    return sorted(skills)


def parse_resume_file(file_path: str) -> dict:
    """Parse a resume file and return structured content."""
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".pdf":
        raw_text = _extract_text_from_pdf(file_path)
    elif ext in (".docx", ".doc"):
        raw_text = _extract_text_from_docx(file_path)
    else:
        raise ValueError(f"Unsupported file type: {ext}. Only PDF and DOCX are supported.")

    sections = _detect_sections(raw_text)
    skills = _extract_skills(raw_text)

    return {
        "raw_text": raw_text,
        "sections": sections,
        "detected_skills": skills,
    }


@tool
async def parse_resume(file_id: str) -> str:
    """Parse an uploaded resume file and return its structured content including sections and detected skills.

    Args:
        file_id: The identifier of the uploaded resume file.
    """
    import tempfile
    from database.mongo import MongoDB

    # The resume is already parsed at upload time and stored in the resumes collection.
    # Try to find it by file_id first (fast path).
    file_meta = await MongoDB.get_file(file_id)
    if not file_meta:
        return f"Error: No file found with id '{file_id}'. Please upload a resume first."

    # Check if we have a pre-parsed version in the resumes collection
    session_id = file_meta.get("session_id")
    if session_id:
        resume_doc = await MongoDB.get_resume(session_id)
        if resume_doc and resume_doc.get("parsed_text"):
            return f"## Resume Analysis\n\n{resume_doc['parsed_text']}"

    # Fallback: retrieve from GridFS and parse on the fly
    result = await MongoDB.retrieve_file(file_id)
    if not result:
        return f"Error: File content not found for id '{file_id}'."

    data, meta = result
    filename = meta.get("filename", "resume.pdf")
    ext = os.path.splitext(filename)[1].lower()

    # Write to temp file for parsing
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name

    try:
        parsed = parse_resume_file(tmp_path)

        output_parts = ["## Resume Analysis\n"]

        if parsed["detected_skills"]:
            output_parts.append(f"**Detected Skills:** {', '.join(parsed['detected_skills'])}\n")

        for section_name, content in parsed["sections"].items():
            if section_name == "other":
                continue
            output_parts.append(f"### {section_name.title()}\n{content}\n")

        if "other" in parsed["sections"] and parsed["sections"]["other"]:
            output_parts.append(f"### Additional Content\n{parsed['sections']['other']}\n")

        return "\n".join(output_parts)

    except Exception as e:
        logger.error("Failed to parse resume file_id='%s': %s", file_id, e)
        return f"Error parsing resume: {e}"
    finally:
        os.unlink(tmp_path)
