from urllib.parse import unquote, urlparse

import aiohttp
from sanic.log import logger

from .. import settings


def authenticated(request) -> bool:
    api_key = _get_api_key(request)
    if api_key:
        api_mask = api_key[:2] + "***" + api_key[-2:]
        logger.info(f"Authenticated with {api_mask}")
        if api_key in settings.API_KEYS:
            return True
    return False


def get_watermark(request, watermark: str) -> tuple[str, bool]:
    if authenticated(request):
        return "", False

    if watermark == settings.DISABLED_WATERMARK:
        referer = _get_referer(request)
        logger.info(f"Watermark removal referer: {referer}")
        if referer:
            domain = urlparse(referer).netloc
            if domain in settings.ALLOWED_WATERMARKS:
                return "", False

        return settings.DEFAULT_WATERMARK, True

    if watermark:
        if watermark == settings.DEFAULT_WATERMARK:
            logger.warning(f"Redundant watermark: {watermark}")
            return watermark, True

        if watermark not in settings.ALLOWED_WATERMARKS:
            logger.warning(f"Unknown watermark: {watermark}")
            return settings.DEFAULT_WATERMARK, True

        return watermark, False

    return settings.DEFAULT_WATERMARK, False


async def track(request, lines: list[str]):
    text = " ".join(lines).strip()
    trackable = not any(
        name in request.args for name in ["height", "width", "watermark"]
    )
    if text and trackable and settings.REMOTE_TRACKING_URL:
        async with aiohttp.ClientSession() as session:
            params = dict(
                text=text,
                client=_get_referer(request) or settings.BASE_URL,
                result=unquote(request.url),
            )
            logger.info(f"Tracking request: {params}")
            headers = {"X-API-KEY": _get_api_key(request) or ""}
            response = await session.get(
                settings.REMOTE_TRACKING_URL, params=params, headers=headers
            )
            if response.status != 200:
                try:
                    message = await response.json()
                except aiohttp.client_exceptions.ContentTypeError:
                    message = response.text
                logger.error(f"Tracker response: {message}")


async def search(request, text: str) -> list[dict]:
    if settings.REMOTE_TRACKING_URL:
        async with aiohttp.ClientSession() as session:
            params = dict(
                text=text,
                client=_get_referer(request) or settings.BASE_URL,
            )
            logger.info(f"Searching for results: {text}")
            headers = {"X-API-KEY": _get_api_key(request) or ""}
            response = await session.get(
                settings.REMOTE_TRACKING_URL, params=params, headers=headers
            )
            assert response.status == 200
            return await response.json()
    return []


def _get_referer(request):
    referer = request.headers.get("referer") or request.args.get("referer")
    if referer and referer.startswith(settings.BASE_URL) and "/docs/" not in referer:
        referer = None
    return referer


def _get_api_key(request):
    return request.headers.get("x-api-key")
