import httpx
from openai import AsyncOpenAI
from anthropic import AsyncAnthropic

from bot.config import config, Provider


def _get_openai_client(provider: Provider) -> AsyncOpenAI:
    return AsyncOpenAI(base_url=provider.base_url, api_key=provider.api_key)


def _get_anthropic_client(provider: Provider) -> AsyncAnthropic:
    return AsyncAnthropic(base_url=provider.base_url, api_key=provider.api_key)


async def fetch_models(provider: Provider) -> list[str]:
    """Fetch available models from provider's /v1/models endpoint."""
    url = provider.base_url.rstrip("/")
    if not url.endswith("/v1"):
        url += "/v1"
    url += "/models"

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            url,
            headers={"Authorization": f"Bearer {provider.api_key}"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

    models = []
    for item in data.get("data", []):
        models.append(item["id"])
    return sorted(models)


async def stream_chat(messages: list[dict], model: str):
    provider = config.get_provider_for_model(model)
    if not provider:
        raise ValueError(f"No provider found for model: {model}")

    if provider.api_type == "openai":
        async for chunk in _stream_openai(messages, model, provider):
            yield chunk
    elif provider.api_type == "anthropic":
        async for chunk in _stream_anthropic(messages, model, provider):
            yield chunk
    else:
        raise ValueError(f"Unknown api_type: {provider.api_type}")


async def _stream_openai(messages: list[dict], model: str, provider: Provider):
    client = _get_openai_client(provider)
    stream = await client.chat.completions.create(
        model=model,
        messages=messages,
        stream=True,
    )
    async for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content


async def chat_once(messages: list[dict], model: str) -> str:
    """Non-streaming single response for internal use (compress, etc.)."""
    provider = config.get_provider_for_model(model)
    if not provider:
        raise ValueError(f"No provider found for model: {model}")

    if provider.api_type == "openai":
        client = _get_openai_client(provider)
        resp = await client.chat.completions.create(model=model, messages=messages)
        return resp.choices[0].message.content or ""
    elif provider.api_type == "anthropic":
        client = _get_anthropic_client(provider)
        system_prompt = None
        api_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_prompt = msg["content"]
            else:
                api_messages.append({"role": msg["role"], "content": msg["content"]})
        kwargs = {"model": model, "messages": api_messages, "max_tokens": 4096}
        if system_prompt:
            kwargs["system"] = system_prompt
        resp = await client.messages.create(**kwargs)
        return resp.content[0].text if resp.content else ""
    else:
        raise ValueError(f"Unknown api_type: {provider.api_type}")


async def _stream_anthropic(messages: list[dict], model: str, provider: Provider):
    client = _get_anthropic_client(provider)

    system_prompt = None
    api_messages = []
    for msg in messages:
        if msg["role"] == "system":
            system_prompt = msg["content"]
        else:
            api_messages.append({"role": msg["role"], "content": msg["content"]})

    kwargs = {"model": model, "messages": api_messages, "max_tokens": 4096}
    if system_prompt:
        kwargs["system"] = system_prompt

    async with client.messages.stream(**kwargs) as stream:
        async for text in stream.text_stream:
            yield text
