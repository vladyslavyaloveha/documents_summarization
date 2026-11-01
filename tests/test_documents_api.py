from uuid import UUID, uuid4

from conftest import ApiClientFactory
from httpx import AsyncClient
from redis.asyncio import Redis

from docparser.config import Settings
from docparser.models import Page
from docparser.storage.repository import DocumentRepository

type MultipartFiles = list[tuple[str, tuple[str, bytes, str]]]


def _pdf_files(pdf: bytes, count: int = 1) -> MultipartFiles:
    return [("files", (f"doc-{i}.pdf", pdf, "application/pdf")) for i in range(count)]


async def test_upload_stores_and_queues_each_pdf(
    api_client: AsyncClient, redis: Redis, settings: Settings, sample_pdf: bytes
) -> None:
    response = await api_client.post(
        "/api/documents", files=_pdf_files(sample_pdf, 2), data={"parser": "pypdf"}
    )

    assert response.status_code == 202
    documents = response.json()
    assert [doc["status"] for doc in documents] == ["queued", "queued"]
    assert [doc["filename"] for doc in documents] == ["doc-0.pdf", "doc-1.pdf"]
    jobs = await redis.xrange(settings.stream_name)
    assert [fields["doc_id"] for _, fields in jobs] == [doc["id"] for doc in documents]
    for doc in documents:
        assert (settings.upload_dir / f"{doc['id']}.pdf").read_bytes() == sample_pdf


async def test_upload_defaults_to_pypdf(
    api_client: AsyncClient, sample_pdf: bytes
) -> None:
    response = await api_client.post("/api/documents", files=_pdf_files(sample_pdf))

    assert response.status_code == 202
    assert response.json()[0]["parser"] == "pypdf"


async def test_upload_keeps_only_the_base_filename(
    api_client: AsyncClient, sample_pdf: bytes
) -> None:
    files = [("files", ("../../etc/report.pdf", sample_pdf, "application/pdf"))]

    response = await api_client.post("/api/documents", files=files)

    assert response.json()[0]["filename"] == "report.pdf"


async def test_upload_rejects_non_pdf_without_queueing_anything(
    api_client: AsyncClient, redis: Redis, settings: Settings, sample_pdf: bytes
) -> None:
    files = [
        *_pdf_files(sample_pdf),
        ("files", ("notes.txt", b"plain text", "text/plain")),
    ]

    response = await api_client.post("/api/documents", files=files)

    assert response.status_code == 415
    assert await redis.exists(settings.stream_name) == 0
    assert not settings.upload_dir.exists() or not any(settings.upload_dir.iterdir())


async def test_upload_rejects_file_over_size_limit(
    make_api_client: ApiClientFactory, settings: Settings, sample_pdf: bytes
) -> None:
    limited = settings.model_copy(update={"max_upload_size_bytes": len(sample_pdf) - 1})

    async with make_api_client(limited) as client:
        response = await client.post("/api/documents", files=_pdf_files(sample_pdf))

    assert response.status_code == 413


async def test_upload_rejects_too_many_files(
    make_api_client: ApiClientFactory, settings: Settings, sample_pdf: bytes
) -> None:
    limited = settings.model_copy(update={"max_files_per_upload": 2})

    async with make_api_client(limited) as client:
        response = await client.post("/api/documents", files=_pdf_files(sample_pdf, 3))

    assert response.status_code == 422


async def test_upload_rejects_unknown_parser(
    api_client: AsyncClient, sample_pdf: bytes
) -> None:
    response = await api_client.post(
        "/api/documents", files=_pdf_files(sample_pdf), data={"parser": "gpt-5-mini"}
    )

    assert response.status_code == 422


async def test_get_returns_queued_document_without_pages(
    api_client: AsyncClient, sample_pdf: bytes
) -> None:
    created = (
        await api_client.post("/api/documents", files=_pdf_files(sample_pdf))
    ).json()[0]

    response = await api_client.get(f"/api/documents/{created['id']}")

    assert response.status_code == 200
    assert response.json()["status"] == "queued"
    assert response.json()["pages"] == []


async def test_get_returns_pages_of_finished_document(
    api_client: AsyncClient, repository: DocumentRepository, sample_pdf: bytes
) -> None:
    created = (
        await api_client.post("/api/documents", files=_pdf_files(sample_pdf))
    ).json()[0]
    document_id = UUID(created["id"])
    await repository.save_pages(document_id, [Page(number=1, markdown="Hello")])
    await repository.mark_done(document_id, summary="A greeting.", summary_error=None)

    body = (await api_client.get(f"/api/documents/{created['id']}")).json()

    assert body["status"] == "done"
    assert body["page_count"] == 1
    assert body["pages"] == [{"number": 1, "markdown": "Hello"}]
    assert body["summary"] == "A greeting."


async def test_get_unknown_document_is_404(api_client: AsyncClient) -> None:
    response = await api_client.get(f"/api/documents/{uuid4()}")

    assert response.status_code == 404


async def test_get_rejects_malformed_id(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/documents/not-a-uuid")

    assert response.status_code == 422


async def test_lists_available_parsers(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/parsers")

    assert response.json() == ["pypdf"]


async def test_batch_get_returns_known_documents(
    api_client: AsyncClient, sample_pdf: bytes
) -> None:
    created = (
        await api_client.post("/api/documents", files=_pdf_files(sample_pdf, 2))
    ).json()
    ids = [doc["id"] for doc in created] + [str(uuid4())]

    response = await api_client.get("/api/documents", params={"ids": ",".join(ids)})

    assert response.status_code == 200
    assert [doc["id"] for doc in response.json()] == ids[:2]


async def test_batch_get_rejects_malformed_ids(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/documents", params={"ids": "a,b"})

    assert response.status_code == 422


async def test_gemini_parser_needs_api_key(
    api_client: AsyncClient, sample_pdf: bytes
) -> None:
    response = await api_client.post(
        "/api/documents", files=_pdf_files(sample_pdf), data={"parser": "gemini"}
    )

    assert response.status_code == 422


async def test_event_stream_reports_finished_document_and_closes(
    api_client: AsyncClient, repository: DocumentRepository, sample_pdf: bytes
) -> None:
    created = (
        await api_client.post("/api/documents", files=_pdf_files(sample_pdf))
    ).json()[0]
    document_id = UUID(created["id"])
    await repository.save_pages(document_id, [Page(number=1, markdown="Hello")])
    await repository.mark_done(document_id, summary=None, summary_error=None)

    response = await api_client.get("/api/events", params={"ids": created["id"]})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: status" in response.text
    assert '"status":"done"' in response.text.replace(" ", "")
