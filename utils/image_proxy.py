from __future__ import annotations

import asyncio
import ipaddress
import os
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx


MAX_IMAGE_BYTES = max(1, int(os.getenv("IMAGE_PROXY_MAX_BYTES", str(12 * 1024 * 1024))))
MAX_REDIRECTS = max(0, min(8, int(os.getenv("IMAGE_PROXY_MAX_REDIRECTS", "4"))))


@dataclass(frozen=True)
class ImageProxyError(Exception):
    code: str
    status_code: int = 400

    def __str__(self) -> str:
        return self.code


def _blocked_ip(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return True
    return not ip.is_global


def _validate_url_shape(value: str) -> tuple[str, int]:
    parsed = urlparse(str(value or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ImageProxyError("invalid_image_url", 400)
    if parsed.username is not None or parsed.password is not None:
        raise ImageProxyError("blocked_image_host", 400)

    hostname = parsed.hostname.strip().lower().rstrip(".")
    if not hostname or hostname == "localhost" or hostname.endswith(".local"):
        raise ImageProxyError("blocked_image_host", 400)

    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise ImageProxyError("invalid_image_url", 400) from exc
    return hostname, int(port)


async def _assert_public_destination(value: str) -> None:
    hostname, port = _validate_url_shape(value)

    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None

    if literal is not None:
        if not literal.is_global:
            raise ImageProxyError("blocked_image_host", 400)
        return

    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(
            hostname,
            port,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
        )
    except OSError as exc:
        raise ImageProxyError("image_host_unresolved", 502) from exc

    addresses = {str(info[4][0]).split("%", 1)[0] for info in infos if info and info[4]}
    if not addresses or any(_blocked_ip(address) for address in addresses):
        raise ImageProxyError("blocked_image_host", 400)


def _sniff_image_type(content: bytes) -> str | None:
    head = bytes(content[:32])
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if len(head) >= 12 and head[4:8] == b"ftyp" and head[8:12] in {b"avif", b"avis"}:
        return "image/avif"
    return None


async def fetch_public_image(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: httpx.Timeout | None = None,
) -> tuple[bytes, str, str]:
    """Fetch an internet image while blocking private-network destinations and oversized bodies.

    Returns (content, media_type, final_url). Redirect targets are revalidated before every hop.
    """
    current_url = str(url or "").strip()
    request_headers = dict(headers or {})
    timeout = timeout or httpx.Timeout(20.0, connect=10.0)

    async with httpx.AsyncClient(
        follow_redirects=False,
        timeout=timeout,
        trust_env=False,
        verify=True,
    ) as client:
        for redirect_count in range(MAX_REDIRECTS + 1):
            await _assert_public_destination(current_url)

            try:
                async with client.stream("GET", current_url, headers=request_headers) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = str(response.headers.get("location") or "").strip()
                        if not location or redirect_count >= MAX_REDIRECTS:
                            raise ImageProxyError("image_redirect_invalid", 502)
                        current_url = urljoin(current_url, location)
                        continue

                    if response.status_code >= 400:
                        raise ImageProxyError("image_source_unavailable", 502)

                    raw_length = str(response.headers.get("content-length") or "").strip()
                    if raw_length:
                        try:
                            content_length = int(raw_length)
                        except ValueError:
                            content_length = 0
                        if content_length > MAX_IMAGE_BYTES:
                            raise ImageProxyError("image_too_large", 413)

                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in response.aiter_bytes():
                        total += len(chunk)
                        if total > MAX_IMAGE_BYTES:
                            raise ImageProxyError("image_too_large", 413)
                        chunks.append(chunk)

                    content = b"".join(chunks)
                    if not content:
                        raise ImageProxyError("image_source_unavailable", 502)

                    declared_type = str(response.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
                    sniffed_type = _sniff_image_type(content)
                    if declared_type.startswith("image/"):
                        media_type = declared_type
                    elif sniffed_type:
                        media_type = sniffed_type
                    else:
                        raise ImageProxyError("invalid_image_content", 415)

                    return content, media_type, current_url
            except ImageProxyError:
                raise
            except (httpx.TimeoutException, httpx.NetworkError, httpx.ProtocolError) as exc:
                raise ImageProxyError("image_fetch_failed", 502) from exc

    raise ImageProxyError("image_redirect_invalid", 502)
