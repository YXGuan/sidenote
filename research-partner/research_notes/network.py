"""Small HTTP client with verified TLS, bounded reads, and transient retries."""
from __future__ import annotations

import ipaddress
import json
import os
from pathlib import Path
import socket
import ssl
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener


def tls_context():
    # python.org's macOS installer can lack its optional certifi symlink. Use
    # the OS CA bundle in that case; certificate verification stays enabled.
    paths = ssl.get_default_verify_paths()
    if sys.platform == "darwin" and not paths.cafile and not os.environ.get("SSL_CERT_FILE") and Path("/etc/ssl/cert.pem").exists():
        return ssl.create_default_context(cafile="/etc/ssl/cert.pem")
    return ssl.create_default_context()


def public_url(url):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError("Metadata retrieval requires a public HTTPS URL")
    addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError("Metadata retrieval cannot access a local or private address")


class SafeRedirect(HTTPRedirectHandler):
    def __init__(self, public_only=False, authenticated_host=None):
        self.public_only = public_only
        self.authenticated_host = authenticated_host

    def redirect_request(self, request, fp, code, msg, headers, newurl):
        if self.authenticated_host and urlsplit(newurl).netloc != self.authenticated_host:
            raise ValueError("Refusing to forward API credentials to another host")
        if self.public_only:
            public_url(newurl)
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def request(url, *, token=None, api_headers=None, public_only=False, data=None, content_type=None, attempts=3, max_bytes=2_000_000, sleep=time.sleep):
    if public_only:
        public_url(url)
    headers = {"User-Agent": "ResearchNotes/0.1 (personal Hypothesis companion)", "Accept": "application/json, text/html;q=0.8"}
    if api_headers:
        allowed = {"api.openalex.org": {"Authorization"}, "api.semanticscholar.org": {"x-api-key"}}
        if urlsplit(url).scheme != "https" or set(api_headers) - allowed.get(urlsplit(url).hostname, set()):
            raise ValueError("Scholarly credentials require their official HTTPS API host")
        headers.update(api_headers)
    if token:
        if urlsplit(url).scheme != "https" or urlsplit(url).hostname != "hypothes.is":
            raise ValueError("Hypothesis tokens can only be sent to https://hypothes.is")
        headers["Authorization"] = "Bearer " + token
    if data is not None:
        if isinstance(data, (str, bytes)):
            headers["Content-Type"] = content_type or "text/plain"
            data = data.encode() if isinstance(data, str) else data
        else:
            headers["Content-Type"] = content_type or "application/json"
            data = json.dumps(data).encode()
    opener = build_opener(HTTPSHandler(context=tls_context()), SafeRedirect(public_only, urlsplit(url).netloc if token or api_headers else None))
    for attempt in range(attempts):
        try:
            with opener.open(Request(url, data=data, headers=headers), timeout=25) as response:
                body = response.read(max_bytes + 1)
                if len(body) > max_bytes:
                    raise ValueError("Response exceeded the size limit")
                return body, response.headers.get("Content-Type", "")
        except HTTPError as error:
            if error.code not in (429, 500, 502, 503, 504) or attempt == attempts - 1:
                # Do not include request headers, tokens, or response bodies.
                raise RuntimeError(f"Remote request failed (HTTP {error.code})") from None
            try:
                delay = min(30, max(1, int(error.headers.get("Retry-After", "1"))))
            except ValueError:
                delay = 2 ** attempt
        except (URLError, TimeoutError, OSError):
            if attempt == attempts - 1:
                raise RuntimeError("Remote request failed; check connectivity and TLS certificates") from None
            delay = 2 ** attempt
        sleep(delay)


def get_json(url, **kwargs):
    body, _ = request(url, **kwargs)
    return json.loads(body)
