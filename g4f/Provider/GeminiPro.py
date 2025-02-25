from __future__ import annotations

import base64
import json
from aiohttp import ClientSession

from ..typing import AsyncResult, Messages, ImageType
from .base_provider import AsyncGeneratorProvider, ProviderModelMixin
from ..image import to_bytes, is_accepted_format
from ..errors import MissingAuthError

class GeminiPro(AsyncGeneratorProvider, ProviderModelMixin):
    url = "https://ai.google.dev"
    working = True
    supports_message_history = True
    needs_auth = True
    default_model = "gemini-pro"
    models = ["gemini-pro", "gemini-pro-vision"]

    @classmethod
    async def create_async_generator(
        cls,
        model: str,
        messages: Messages,
        stream: bool = False,
        proxy: str = None,
        api_key: str = None,
        api_base: str = None,
        image: ImageType = None,
        **kwargs
    ) -> AsyncResult:
        model = "gemini-pro-vision" if not model and image else model
        model = cls.get_model(model)

        if not api_key:
            raise MissingAuthError('Missing "api_key"')
        if not api_base:
            api_base = f"https://generativelanguage.googleapis.com/v1beta"

        method = "streamGenerateContent" if stream else "generateContent"
        url = f"{api_base.rstrip('/')}/models/{model}:{method}"
        headers = None
        if api_base:
            headers = {f"Authorization": "Bearer {api_key}"}
        else:
            url += f"?key={api_key}"

        async with ClientSession(headers=headers) as session:
            contents = [
                {
                    "role": "model" if message["role"] == "assistant" else message["role"],
                    "parts": [{"text": message["content"]}]
                }
                for message in messages
            ]
            if image:
                image = to_bytes(image)
                contents[-1]["parts"].append({
                    "inline_data": {
                        "mime_type": is_accepted_format(image),
                        "data": base64.b64encode(image).decode()
                    }
                })
            data = {
                "contents": contents,
                "generationConfig": {
                    "stopSequences": kwargs.get("stop"),
                    "temperature": kwargs.get("temperature"),
                    "maxOutputTokens": kwargs.get("max_tokens"),
                    "topP": kwargs.get("top_p"),
                    "topK": kwargs.get("top_k"),
                }
            }
            async with session.post(url, json=data, proxy=proxy) as response:
                if not response.ok:
                    data = await response.json()
                    raise RuntimeError(data[0]["error"]["message"])
                if stream:
                    lines = []
                    async for chunk in response.content:
                        if chunk == b"[{\n":
                            lines = [b"{\n"]
                        elif chunk == b",\r\n" or chunk == b"]":
                            try:
                                data = json.loads(b"".join(lines))
                                yield data["candidates"][0]["content"]["parts"][0]["text"]
                            except:
                                data = data.decode() if isinstance(data, bytes) else data
                                raise RuntimeError(f"Read chunk failed: {data}")
                            lines = []
                        else:
                            lines.append(chunk)
                else:
                    data = await response.json()
                    yield data["candidates"][0]["content"]["parts"][0]["text"]