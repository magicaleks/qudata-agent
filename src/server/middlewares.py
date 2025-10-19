import json

import falcon

from src import consts
from src.storage.secure import get_agent_secret


class JSONMiddleware:

    def process_request(self, req: falcon.Request, resp: falcon.Response):
        if req.content_length in (None, 0):
            req.context["json"] = None
            return

        content_type = (req.content_type or "").lower()
        if "application/json" in content_type:
            try:
                body = req.bounded_stream.read()
                if body:
                    req.context["json"] = json.loads(body.decode("utf-8"))
                else:
                    req.context["json"] = None
            except json.JSONDecodeError:
                # TODO: log, but unreachable
                pass
        else:
            req.context["json"] = None

    def process_response(
	    self,
        req: falcon.Request,
        resp: falcon.Response,
        resource,
        req_succeeded: bool,
    ):
        if "result" in resp.context:
            resp.text = json.dumps(
                resp.context["result"],
                ensure_ascii=False,
                indent=None,
                separators=(",", ":"),
            )
            resp.content_type = "application/json; charset=utf-8"

        if not req_succeeded and resp.status >= falcon.HTTP_400:
            try:
                json.loads(resp.text or "")
            except Exception:
                resp.text = json.dumps(
                    {"error": resp.status},
                    ensure_ascii=False,
                )
                # TODO: log exc
                resp.content_type = "application/json; charset=utf-8"


class AuthMiddleware:

    def process_request(self, req: falcon.Request, resp: falcon.Response):
        if req.method == "OPTIONS":
            return

        key = req.get_header(consts.APP_HEADER_NAME)
        if not key or key != get_agent_secret():
            raise falcon.HTTPUnauthorized(
                title="Unauthorized",
            )
