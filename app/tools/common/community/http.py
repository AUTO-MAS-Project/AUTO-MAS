#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""社区请求的 DNS 故障回退，不接管系统代理或修改系统 DNS。"""

import ipaddress
import time

import httpx


class CommunityHTTPTransport(httpx.AsyncBaseTransport):
    """直连建立连接失败时，通过 HTTPS DNS 重试；显式代理仍交给代理解析。"""

    def __init__(self, proxy: str | httpx.Proxy | None = None) -> None:
        self._transport = httpx.AsyncHTTPTransport(proxy=proxy, trust_env=False)
        self._uses_proxy = proxy is not None
        self._resolved: dict[str, tuple[str, float]] = {}
        self._resolved_transports: dict[str, httpx.AsyncHTTPTransport] = {}

    async def _resolve(self, hostname: str) -> list[tuple[str, float]]:
        # 固定引导 IP 避免 DoH 本身再次经过被 TUN/Fake-IP 影响的本地 DNS。
        # Host 与 TLS SNI 都保留服务域名，不能为绕过 DNS 错误关闭证书校验。
        async with httpx.AsyncClient(trust_env=False, timeout=3.0) as client:
            for address in ("223.5.5.5", "223.6.6.6"):
                try:
                    response = await client.get(
                        f"https://{address}/resolve",
                        params={"name": hostname, "type": "A"},
                        headers={
                            "Host": "dns.alidns.com",
                            "Accept": "application/dns-json",
                        },
                        extensions={"sni_hostname": "dns.alidns.com"},
                    )
                    response.raise_for_status()
                    payload = response.json()
                    if not isinstance(payload, dict) or payload.get("Status") != 0:
                        continue
                    addresses = []
                    for answer in payload.get("Answer", []):
                        if not isinstance(answer, dict) or answer.get("type") != 1:
                            continue
                        ip = ipaddress.ip_address(answer.get("data", ""))
                        if not ip.is_global:
                            continue
                        ttl = max(0, min(int(answer.get("TTL", 60)), 300))
                        addresses.append((str(ip), time.monotonic() + ttl))
                    if addresses:
                        return addresses[:2]
                except (httpx.HTTPError, ValueError, TypeError):
                    continue
        return []

    async def _send_to_address(
        self, request: httpx.Request, address: str
    ) -> httpx.Response:
        # 只在连接阶段失败后重试，原请求尚未发送；读写失败不能重放签到 POST。
        resolved_request = httpx.Request(
            request.method,
            request.url.copy_with(host=address),
            headers=request.headers,
            content=await request.aread(),
            extensions={**request.extensions, "sni_hostname": request.url.host},
        )
        # 不同域名可能解析到同一 CDN IP；独立连接池保证每个域名都验证自己的证书。
        transport = self._resolved_transports.get(request.url.host)
        if transport is None:
            transport = httpx.AsyncHTTPTransport(trust_env=False)
            self._resolved_transports[request.url.host] = transport
        return await transport.handle_async_request(resolved_request)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        hostname = request.url.host
        cached = self._resolved.get(hostname)
        try:
            if cached and time.monotonic() < cached[1]:
                return await self._send_to_address(request, cached[0])
            return await self._transport.handle_async_request(request)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ProxyError) as error:
            self._resolved.pop(hostname, None)
            if not self._uses_proxy and request.url.scheme == "https":
                for address, expires_at in await self._resolve(hostname):
                    try:
                        response = await self._send_to_address(request, address)
                    except (httpx.ConnectError, httpx.ConnectTimeout):
                        continue
                    self._resolved[hostname] = (address, expires_at)
                    return response
            reason = (
                "社区代理连接失败，请检查 MAS 中的代理地址与代理服务"
                if self._uses_proxy
                else "社区网络连接失败，加密 DNS 回退未成功，请检查系统代理/TUN 的 DNS 设置或关闭代理后重试"
            )
            raise httpx.ConnectError(reason, request=request) from error

    async def aclose(self) -> None:
        await self._transport.aclose()
        for transport in self._resolved_transports.values():
            await transport.aclose()


def create_community_client(
    proxy: str | httpx.Proxy | None = None,
    *,
    cookies: dict[str, str] | None = None,
) -> httpx.AsyncClient:
    """创建保留显式代理、忽略环境代理的社区 HTTP 客户端。"""

    return httpx.AsyncClient(
        transport=CommunityHTTPTransport(proxy),
        trust_env=False,
        cookies=cookies,
    )
