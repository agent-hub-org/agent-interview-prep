import logging
import os
from datetime import datetime, timezone

from agent_sdk.database.mongo import BaseMongoDatabase
from agent_sdk.database.gridfs_mixin import GridFSMixin

logger = logging.getLogger("agent_interview_prep.mongo")

_DB_NAME = os.getenv("MONGO_DB_NAME", "agent_interview_prep")


class MongoDB(GridFSMixin, BaseMongoDatabase):

    @classmethod
    def db_name(cls) -> str:
        return _DB_NAME

    @classmethod
    def _db(cls):
        return cls.get_client()[cls.db_name()]

    @classmethod
    def _files(cls):
        return cls._db()["files"]

    @classmethod
    def _resumes(cls):
        return cls._db()["resumes"]

    @classmethod
    def _codebases(cls):
        return cls._db()["codebases"]

    # ── Resume persistence ──

    @classmethod
    async def save_resume(
        cls,
        session_id: str,
        file_id: str,
        filename: str,
        parsed_text: str,
    ) -> None:
        doc = {
            "session_id": session_id,
            "file_id": file_id,
            "filename": filename,
            "parsed_text": parsed_text,
            "created_at": datetime.now(timezone.utc),
        }
        # Upsert — one resume per session
        await cls._resumes().update_one(
            {"session_id": session_id},
            {"$set": doc},
            upsert=True,
        )
        logger.info("Saved resume for session='%s', file_id='%s'", session_id, file_id)

    @classmethod
    async def get_resume(cls, session_id: str) -> dict | None:
        return await cls._resumes().find_one(
            {"session_id": session_id},
            {"_id": 0},
        )

    # ── Codebase persistence ──

    @classmethod
    async def store_codebase(cls, session_id: str, codebase_doc: dict) -> None:
        """Store a fetched GitHub repo codebase for the session. Upserts — one codebase per session."""
        doc = {
            "session_id": session_id,
            "repo_url": codebase_doc.get("repo_url"),
            "repo_name": codebase_doc.get("repo_name"),
            "owner": codebase_doc.get("owner"),
            "language": codebase_doc.get("language"),
            "description": codebase_doc.get("description"),
            "file_tree": codebase_doc.get("file_tree", []),
            "key_files": codebase_doc.get("key_files", []),
            "summary": codebase_doc.get("summary", ""),
            "total_files": codebase_doc.get("total_files", 0),
            "created_at": datetime.now(timezone.utc),
        }
        await cls._codebases().update_one(
            {"session_id": session_id},
            {"$set": doc},
            upsert=True,
        )
        logger.info(
            "Stored codebase for session='%s', repo='%s/%s', files=%d",
            session_id,
            codebase_doc.get("owner"),
            codebase_doc.get("repo_name"),
            codebase_doc.get("total_files", 0),
        )

    @classmethod
    async def get_codebase(cls, session_id: str) -> dict | None:
        """Retrieve the stored codebase document for a session."""
        return await cls._codebases().find_one(
            {"session_id": session_id},
            {"_id": 0},
        )

    @classmethod
    async def get_file(cls, file_id: str) -> dict | None:
        return await cls._files().find_one(
            {"file_id": file_id},
            {"_id": 0},
        )

    @classmethod
    async def list_files(cls, session_id: str) -> list[dict]:
        cursor = cls._files().find(
            {"session_id": session_id},
            {"_id": 0, "file_id": 1, "filename": 1, "file_type": 1, "created_at": 1},
        ).sort("created_at", 1)
        return await cursor.to_list(length=50)

    # ── Mock interview scores ──

    @classmethod
    def _scores(cls):
        return cls._db()["mock_scores"]

    @classmethod
    async def save_score(
        cls,
        user_id: str | None,
        session_id: str,
        question: str,
        topic: str,
        accuracy: int,
        clarity: int,
        depth: int,
        star: int | None = None,
        notes: str = "",
    ) -> None:
        avg = round(sum(filter(None, [accuracy, clarity, depth, star])) /
                    len([x for x in [accuracy, clarity, depth, star] if x is not None]), 2)
        doc = {
            "user_id": user_id,
            "session_id": session_id,
            "question": question[:300],
            "topic": topic,
            "accuracy": accuracy,
            "clarity": clarity,
            "depth": depth,
            "star": star,
            "avg_score": avg,
            "notes": notes,
            "created_at": datetime.now(timezone.utc),
        }
        await cls._scores().insert_one(doc)

    @classmethod
    async def get_scores(cls, session_id: str, user_id: str | None = None) -> list[dict]:
        flt: dict = {"session_id": session_id}
        if user_id:
            flt["user_id"] = user_id
        cursor = cls._scores().find(flt, {"_id": 0}).sort("created_at", 1)
        return await cursor.to_list(length=200)

    @classmethod
    async def get_user_scores(cls, user_id: str) -> list[dict]:
        cursor = cls._scores().find({"user_id": user_id}, {"_id": 0}).sort("created_at", -1)
        return await cursor.to_list(length=500)

    # ── Share tokens for notes ──

    @classmethod
    def _share_tokens(cls):
        return cls._db()["share_tokens"]

    @classmethod
    async def create_share_token(cls, file_id: str, user_id: str | None = None) -> str:
        import uuid
        token = uuid.uuid4().hex
        await cls._share_tokens().insert_one({
            "token": token,
            "file_id": file_id,
            "user_id": user_id,
            "created_at": datetime.now(timezone.utc),
        })
        return token

    @classmethod
    async def resolve_share_token(cls, token: str) -> str | None:
        doc = await cls._share_tokens().find_one({"token": token}, {"_id": 0})
        return doc["file_id"] if doc else None

    @classmethod
    async def ensure_indexes(cls) -> None:
        await super().ensure_indexes()
        db = cls._db()
        await db["resumes"].create_index("created_at", expireAfterSeconds=7_776_000)
        await db["codebases"].create_index("created_at", expireAfterSeconds=7_776_000)
        await db["files"].create_index("created_at", expireAfterSeconds=2_592_000)
        await db["fs.files"].create_index("uploadDate", expireAfterSeconds=2_592_000)
        await db["mock_scores"].create_index([("user_id", 1), ("session_id", 1)])
        await db["mock_scores"].create_index("created_at", expireAfterSeconds=15_552_000)
        await db["share_tokens"].create_index("created_at", expireAfterSeconds=2_592_000)
