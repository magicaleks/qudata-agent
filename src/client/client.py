from typing import Any

import backoff
import httpx

from src import consts
from src.client.models import AgentResponse, CreateHost, Incident, InitAgent, Stats
from src.storage.secure import get_agent_secret, set_agent_secret
from src.utils.dto import from_json, to_json


class HttpClient:

    def __init__(self, base_url: str = consts.API_BASE_URL):
        self._client = httpx.Client(base_url=base_url)
        self._inited = False
        secret = get_agent_secret()
        if secret:
            self._client.headers.update({consts.APP_HEADER_NAME: secret})

    @backoff.on_exception(backoff.expo, httpx.HTTPError, max_time=60, max_retries=5)
    def _request(
        self,
        method: str,
        path: str,
        json: dict[str, Any] = None,
        params: dict[str, Any] = None,
    ) -> dict:
        response = self._client.request(method, path, json=json, params=params)
        response.raise_for_status()
        return response.json()

    def ping(self) -> bool:
        resp = self._request("GET", "/ping")
        return resp.get("ok", False)

    def init(self, data: InitAgent) -> AgentResponse:
        resp = self._request("POST", "/init", json=to_json(data))
        agent = from_json(AgentResponse, resp)
        # TODO: process errors
        if agent.secret_key:
            set_agent_secret(agent.secret_key)
            self._inited = True
            self._client.headers.update({consts.APP_HEADER_NAME: agent.secret_key})
        return agent

    def send_incident(self, data: Incident) -> None:
        if not self._inited:
            raise RuntimeError("Agent has not been initialized")

        self._request("POST", "/init", json=to_json(data))

    def create_host(self, data: CreateHost) -> None:
        if not self._inited:
            raise RuntimeError("Agent has not been initialized")

        self._request("POST", "/init/host", json=to_json(data))

    def send_stats(self, data: Stats) -> None:
        if not self._inited:
            raise RuntimeError("Agent has not been initialized")

        self._request("POST", "/stats", json=to_json(data))
