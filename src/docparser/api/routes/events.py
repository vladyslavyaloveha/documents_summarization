import json
from collections.abc import AsyncIterator
from typing import Final

from fastapi import APIRouter
from fastapi.sse import EventSourceResponse, ServerSentEvent

from docparser.api.deps import DocumentIdsDep, RedisDep, RepositoryDep
from docparser.models import DocumentStatus
from docparser.storage.repository import events_channel

router = APIRouter(prefix="/api", tags=["events"])

TERMINAL_STATUSES: Final[frozenset[str]] = frozenset(
    {DocumentStatus.DONE.value, DocumentStatus.FAILED.value}
)
POLL_TIMEOUT_SECONDS: Final[float] = 5.0


@router.get("/events", response_class=EventSourceResponse)
async def stream_status_events(
    document_ids: DocumentIdsDep, redis: RedisDep, repository: RepositoryDep
) -> AsyncIterator[ServerSentEvent]:
    async with redis.pubsub() as pubsub:
        await pubsub.subscribe(
            *(events_channel(document_id) for document_id in document_ids)
        )
        waiting: set[str] = set()
        for document_id in document_ids:
            document = await repository.get(document_id)
            if document is None:
                continue
            yield _status_event(str(document_id), document.status.value)
            if document.status.value not in TERMINAL_STATUSES:
                waiting.add(str(document_id))

        while waiting:
            message = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=POLL_TIMEOUT_SECONDS
            )
            if message is None:
                continue
            event = json.loads(message["data"])
            yield _status_event(event["id"], event["status"])
            if event["status"] in TERMINAL_STATUSES:
                waiting.discard(event["id"])


def _status_event(document_id: str, status: str) -> ServerSentEvent:
    return ServerSentEvent(event="status", data={"id": document_id, "status": status})
