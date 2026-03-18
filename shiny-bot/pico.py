"""Shared Pico W communication module."""
import os
import socket

PICO_HOST = os.environ.get("PICO_IP", "YOUR_PICO_IP")
PICO_PORT = int(os.environ.get("PICO_PORT", "8080"))


def post(path: str, body: str = "") -> str:
    """Send a raw HTTP POST to the Pico (fresh connection, no Content-Type header)."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        sock.connect((PICO_HOST, PICO_PORT))

        body_bytes = body.encode() if body else b""
        request = (
            f"POST {path} HTTP/1.1\r\n"
            f"Host: {PICO_HOST}:{PICO_PORT}\r\n"
            f"Content-Length: {len(body_bytes)}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        ).encode() + body_bytes

        sock.sendall(request)
        response = b""

        while True:
            try:
                chunk = sock.recv(1024)
                if not chunk:
                    break
                response += chunk
            except socket.timeout:
                break

        sock.close()

        if not response:
            return "Error: no response from Pico"

        text = response.decode(errors="replace")
        if "\r\n\r\n" in text:
            return text.split("\r\n\r\n", 1)[1].strip()
        return text.strip() if text.strip() else "Error: empty response"

    except (socket.error, socket.timeout) as e:
        return f"Error: {e}"


def send_cmd(command: str) -> str:
    return post("/cmd", command).strip()
