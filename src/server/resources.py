import falcon
from falcon import Request, Response

from src.service.ssh_keys import add_ssh_pubkey


class PingResource:

    @staticmethod
    def on_get(req: Request, resp: Response) -> None:
        resp.status = falcon.HTTP_200
        resp.context["result"] = {"ok": True, "data": None}


class AddSSHResource:

    @staticmethod
    def on_post(req: Request, resp: Response) -> None:
        ssh_pubkey = req.context["json"]["ssh_pubkey"]
        add_ssh_pubkey(ssh_pubkey)
        resp.context["result"] = {"ok": True, "data": None}


class ManageInstancesResource:

    @staticmethod
    def on_get(req: Request, resp: Response) -> None:
        # TODO: get info (ex logs)
        pass

    @staticmethod
    def on_post(req: Request, resp: Response) -> None:
        # TODO: create instance
        pass

    @staticmethod
    def on_put(req: Request, resp: Response) -> None:
        # TODO: manage (start, stop, reboot, etc)
        pass

    @staticmethod
    def on_delete(req: Request, resp: Response) -> None:
        # TODO: remove instance and all user data
        pass


class ShutdownResource:

    @staticmethod
    def on_post(req: Request, resp: Response) -> None:
        #  TODO: stops agent
        pass


class EmergencyResource:

    @staticmethod
    def on_post(req: Request, resp: Response) -> None:
        # TODO: kill all instances and clear data
        pass
