"""Inherited by qualification Python children; no external network or dotenv."""

import ipaddress
import os
import socket


def loopback(host):
    if isinstance(host, bytes):
        host = host.decode("ascii")
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


if os.environ.get("LNF_QUALIFICATION_GUARD") == "1":
    os.environ["PYTHON_DOTENV_DISABLED"] = "1"
    os.environ["LNF_ENV_FILE"] = ""
    os.environ["LNF_DISABLE_DOTENV"] = "1"
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_getaddrinfo = socket.getaddrinfo

    def check(address):
        if isinstance(address, tuple) and not loopback(address[0]):
            raise OSError("qualification permits loopback connections only")

    def connect(self, address):
        check(address)
        return original_connect(self, address)

    def connect_ex(self, address):
        check(address)
        return original_connect_ex(self, address)

    def getaddrinfo(host, *args, **kwargs):
        if host is not None and not loopback(host):
            raise OSError("qualification permits loopback DNS only")
        return original_getaddrinfo(host, *args, **kwargs)

    for name, replacement in (("connect", connect), ("connect_ex", connect_ex)):
        setattr(socket.socket, name, replacement)
    socket.getaddrinfo = getaddrinfo

    original_sendto = socket.socket.sendto

    def sendto(self, data, *args):
        check(args[-1])
        return original_sendto(self, data, *args)

    socket.socket.sendto = sendto

    # gRPC uses native sockets, bypassing Python's socket.connect.
    try:
        import grpc
        import grpc.aio
    except ImportError:
        pass
    else:

        def guarded_channel(factory):
            def channel(target, *args, **kwargs):
                value = target.decode() if isinstance(target, bytes) else target
                host = value.rsplit(":", 1)[0].strip("[]")
                if not loopback(host):
                    raise OSError("qualification permits loopback gRPC only")
                return factory(target, *args, **kwargs)

            return channel

        for api in (grpc, grpc.aio):
            for name in ("secure_channel", "insecure_channel"):
                setattr(api, name, guarded_channel(getattr(api, name)))
