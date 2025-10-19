from falcon import App

from src.server.middlewares import AuthMiddleware, JSONMiddleware
from src.server.resources import (
    AddSSHResource,
    EmergencyResource,
    ManageInstancesResource,
    PingResource,
    ShutdownResource,
)

app = App()

app.add_middleware(JSONMiddleware())
# app.add_middleware(AuthMiddleware())

app.add_route("/ping", PingResource())
app.add_route("/ssh", AddSSHResource())
app.add_route("/instances", ManageInstancesResource())
app.add_route("/shutdown", ShutdownResource())
app.add_route("/emergency", EmergencyResource())
