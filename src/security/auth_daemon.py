import json
import logging
import os
import selectors
import socket
import struct

from src import consts, runtime

sel = selectors.DefaultSelector()


def get_creds(conn):
    creds = conn.getsockopt(
        socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")
    )
    pid, uid, gid = struct.unpack("3i", creds)
    return pid, uid, gid


def check(req, uid):
    uri = (req.get("RequestUri") or req.get("uri") or "").lower()
    if uid == runtime.agent_pid():
        return {"allow": True, "reason": "trusted uid"}
    for x in consts.DOCKER_FORBIDDEN_CMDS:
        if x in uri:
            return {"allow": False, "reason": f"forbidden: {x}"}
    return {"allow": True, "reason": "ok"}


def handle(conn):
    try:
        pid, uid, gid = get_creds(conn)
        data = conn.recv(16384)
        if not data:
            return
        try:
            req = json.loads(data.decode())
        except:
            conn.sendall(b'{"allow":false,"reason":"bad json"}')
            return
        res = check(req, uid)
        conn.sendall(json.dumps(res).encode())
        logging.info(
            "uid=%s %s %s -> %s",
            uid,
            req.get("RequestMethod"),
            req.get("RequestUri"),
            res["allow"],
        )
    except Exception as e:
        try:
            conn.sendall(b'{"allow":false,"reason":"error"}')
        except:
            pass
        logging.error("%s", e)
    finally:
        conn.close()


def accept(sock):
    conn, _ = sock.accept()
    conn.setblocking(False)
    sel.register(conn, selectors.EVENT_READ, read)


def read(conn):
    sel.unregister(conn)
    handle(conn)


def auth_daemon() -> None:
    if os.path.exists(consts.KATAGUARD_SOCK_PATH):
        os.unlink(consts.KATAGUARD_SOCK_PATH)
    os.makedirs(os.path.dirname(consts.KATAGUARD_SOCK_PATH), exist_ok=True)
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.bind(consts.KATAGUARD_SOCK_PATH)
    os.chmod(consts.KATAGUARD_SOCK_PATH, 0o660)
    s.listen(100)
    s.setblocking(False)
    sel.register(s, selectors.EVENT_READ, accept)
    try:
        while True:
            for key, _ in sel.select():
                key.data(key.fileobj)
    except KeyboardInterrupt:
        pass
    finally:
        sel.close()
        s.close()
        if os.path.exists(consts.KATAGUARD_SOCK_PATH):
            os.unlink(consts.KATAGUARD_SOCK_PATH)
