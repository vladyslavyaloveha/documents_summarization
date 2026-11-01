from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from docparser.llm.summarizer import Summarizer


def _recording_model(prompts: list[str]) -> FunctionModel:
    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        request = messages[-1]
        assert isinstance(request, ModelRequest)
        prompt = "".join(str(part.content) for part in request.parts)
        prompts.append(prompt)
        return ModelResponse(parts=[TextPart(f"summary #{len(prompts)}")])

    return FunctionModel(respond)


async def test_short_text_is_summarized_in_one_call() -> None:
    prompts: list[str] = []
    summarizer = Summarizer(_recording_model(prompts), max_chars_per_call=1_000)

    summary = await summarizer.summarize("A short document about Redis Streams.", "DE")

    assert summary == "summary #1"
    assert len(prompts) == 1
    assert "<document>" in prompts[0]
    assert "A short document about Redis Streams." in prompts[0]
    assert "<language>DE</language>" in prompts[0]


async def test_long_text_is_summarized_per_chunk_then_combined() -> None:
    prompts: list[str] = []
    summarizer = Summarizer(
        _recording_model(prompts), max_chars_per_call=200, chunk_overlap_chars=0
    )
    text = "\n\n".join(f"Paragraph {i}: " + "word " * 30 for i in range(4))

    summary = await summarizer.summarize(text, "IT")

    assert len(prompts) > 2
    assert summary == f"summary #{len(prompts)}"
    assert all(f"summary #{i}" in prompts[-1] for i in range(1, len(prompts)))
    assert all("<language>IT</language>" in prompt for prompt in prompts)
