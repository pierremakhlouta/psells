"""A connection the tests can cut: a small local HTTPS proxy each browser
goes through, so a phone's lost signal can be made real.

Playwright can tell a browser it is offline, but WebKit then fails the
navigation itself instead of letting the service worker answer, which a real
iPhone does not. Through this relay, cut() refuses new connections and
closes the open ones, exactly as a server that has gone away; the browser,
not Playwright, finds the network gone. restore() lets it through again.

It only joins two sockets (HTTP CONNECT), so TLS runs from the browser to
nginx untouched and the certificate is checked as it always is.
"""

import select
import socket
import socketserver
import threading


class Relay:
    def __init__(self):
        self._tunnels = set()
        self._lock = threading.Lock()
        self._server = None
        self.port = self._start(0)

    def _start(self, port):
        relay = self

        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                relay._tunnel(self.request)

        socketserver.ThreadingTCPServer.allow_reuse_address = True
        self._server = socketserver.ThreadingTCPServer(("127.0.0.1", port), Handler)
        self._server.daemon_threads = True
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return self._server.server_address[1]

    @property
    def address(self):
        return f"http://127.0.0.1:{self.port}"

    def _tunnel(self, client):
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = client.recv(4096)
            if not chunk:
                return
            head += chunk
        method, target = head.split(b" ", 2)[:2]
        if method != b"CONNECT":
            client.sendall(b"HTTP/1.1 405 Method Not Allowed\r\n\r\n")
            return
        host, port = target.decode().rsplit(":", 1)
        try:
            upstream = socket.create_connection((host, int(port)), timeout=5)
        except OSError:
            client.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
            return
        client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        with self._lock:
            self._tunnels.update({client, upstream})
        try:
            sockets = [client, upstream]
            while True:
                readable, _, _ = select.select(sockets, [], [], 30)
                if not readable:
                    break
                for source in readable:
                    data = source.recv(65536)
                    if not data:
                        return
                    (upstream if source is client else client).sendall(data)
        except OSError:
            return
        finally:
            with self._lock:
                self._tunnels.discard(client)
                self._tunnels.discard(upstream)
            upstream.close()

    def cut(self):
        """No connection: new ones refused, open ones closed."""
        self._server.shutdown()
        self._server.server_close()
        with self._lock:
            for sock in list(self._tunnels):
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                sock.close()
            self._tunnels.clear()

    def restore(self):
        self._start(self.port)

    def close(self):
        self.cut()
