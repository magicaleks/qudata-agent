import os
import signal
import threading
from dataclasses import asdict

import falcon
from falcon import Request, Response

from src.server.models import CreateInstance, ManageInstance
from src.service import instances
from src.service.ssh_keys import add_ssh_pubkey
from src.storage import state as state_manager
from src.utils.dto import from_json
from src.utils.xlogging import get_logger

logger = get_logger(__name__)


class PingResource:

    def on_get(self, req: Request, resp: Response) -> None:
        resp.status = falcon.HTTP_200
        resp.context["result"] = {"ok": True, "data": None}


class AddSSHResource:

    def on_post(self, req: Request, resp: Response) -> None:
        try:
            ssh_pubkey = req.context["json"]["ssh_pubkey"]
            add_ssh_pubkey(ssh_pubkey)
            resp.status = falcon.HTTP_200
            resp.context["result"] = {"ok": True, "data": None}
        except (KeyError, TypeError):
            raise falcon.HTTPBadRequest(
                title="Invalid request",
                description="Missing 'ssh_pubkey' field.",
            )
        except Exception as e:
            logger.error(f"Failed to add SSH key: {e}")
            raise falcon.HTTPInternalServerError(
                title="Internal Error",
                description="Could not process SSH key.",
            )


class ManageInstancesResource:

    def on_get(self, req: Request, resp: Response) -> None:
        state = state_manager.get_current_state()
        response_data = asdict(state)

        if req.get_param_as_bool("logs") and state.container_id:
            success, logs, err = instances.get_instance_logs(state.container_id)
            if success:
                response_data["logs"] = logs
            else:
                response_data["logs_error"] = err

        resp.status = falcon.HTTP_200
        resp.context["result"] = {"ok": True, "data": response_data}

    def on_post(self, req: Request, resp: Response) -> None:

        try:
            create_params = from_json(CreateInstance, req.context.get("json"))
        except Exception as e:
            raise falcon.HTTPBadRequest(
                title="Invalid JSON payload", description=str(e)
            )

        success, data, error = instances.create_new_instance(create_params)

        if success:
            resp.status = falcon.HTTP_201
            resp.context["result"] = {"ok": True, "data": data}
        else:
            resp.status = falcon.HTTP_500
            resp.context["result"] = {"ok": False, "error": error}

    def on_put(self, req: Request, resp: Response) -> None:
        try:
            manage_params = from_json(ManageInstance, req.context.get("json"))
        except Exception as e:
            raise falcon.HTTPBadRequest(
                title="Invalid JSON payload", description=str(e)
            )

        success, error = instances.manage_instance(manage_params)

        if success:
            resp.status = falcon.HTTP_200
            resp.context["result"] = {"ok": True}
        else:
            resp.status = falcon.HTTP_500
            resp.context["result"] = {"ok": False, "error": error}

    def on_delete(self, req: Request, resp: Response) -> None:
        success, error = instances.delete_instance()
        if success:
            resp.status = falcon.HTTP_200
            resp.context["result"] = {"ok": True}
        else:
            resp.status = falcon.HTTP_500
            resp.context["result"] = {"ok": False, "error": error}


class ShutdownResource:

    def on_post(self, req: Request, resp: Response) -> None:
        logger.warning("Shutdown request received. Agent is shutting down...")

        def shutdown_thread():
            threading.Timer(1.0, lambda: os.kill(os.getpid(), signal.SIGINT)).start()

        shutdown_thread()

        resp.status = falcon.HTTP_202
        resp.context["result"] = {"ok": True, "message": "Agent shutdown initiated."}


class EmergencyResource:

    def on_post(self, req: Request, resp: Response) -> None:
        logger.critical("EMERGENCY self-destruct sequence initiated via API!")

        threading.Thread(target=instances.emergency_self_destruct).start()

        resp.status = falcon.HTTP_202
        resp.context["result"] = {
            "ok": True,
            "message": "Emergency self-destruct sequence initiated.",
        }
