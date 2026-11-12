#!/usr/bin/env python3
"""
Bidirectional Wayland/GNOME Clipboard Synchronizer (Text & Images) over SSH.
Uses GTK3 over XWayland (:0) to bypass GNOME Mutter's lack of wlr-data-control,
and streams updates directly over SSH (port 22) so zero firewall or sudo changes are needed.
"""

import os
import sys
import glob
import json
import struct
import hashlib
import threading
import subprocess

# Ensure XWayland backend is used so GNOME Mutter allows background clipboard access
os.environ["GDK_BACKEND"] = "x11"
if "DISPLAY" not in os.environ:
    os.environ["DISPLAY"] = ":0"

if "XAUTHORITY" not in os.environ or not os.path.exists(os.environ.get("XAUTHORITY", "")):
    uid = os.getuid()
    auth_files = sorted(
        glob.glob(f"/run/user/{uid}/.mutter-Xwaylandauth.*"),
        key=os.path.getmtime,
        reverse=True,
    )
    if auth_files:
        os.environ["XAUTHORITY"] = auth_files[0]

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib, GdkPixbuf

MAX_PAYLOAD_BYTES = 50 * 1024 * 1024  # 50 MB max (for high-res screenshots)
STATE_FILE = f"/run/user/{os.getuid()}/lan-clip-sync.sha256"


def compute_hash(kind: str, data: bytes) -> str:
    h = hashlib.sha256()
    h.update(kind.encode("utf-8"))
    h.update(data)
    return h.hexdigest()


def read_last_hash() -> str:
    try:
        with open(STATE_FILE, "r") as f:
            return f.read().strip()
    except Exception:
        return ""


def write_last_hash(digest: str):
    try:
        with open(STATE_FILE, "w") as f:
            f.write(digest)
    except Exception:
        pass


def run_apply_mode():
    """Reads a single framed clipboard payload from stdin and writes it to the local clipboard."""
    raw_len = sys.stdin.buffer.read(4)
    if len(raw_len) < 4:
        return
    (header_len,) = struct.unpack("!I", raw_len)
    header = json.loads(sys.stdin.buffer.read(header_len).decode("utf-8"))
    mime = header["mime"]
    size = int(header["size"])
    digest = header["sha256"]

    if size <= 0 or size > MAX_PAYLOAD_BYTES:
        return
    payload = sys.stdin.buffer.read(size)
    if len(payload) != size:
        return

    if digest == read_last_hash():
        return
    write_last_hash(digest)

    clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
    if mime == "text/plain":
        text = payload.decode("utf-8", errors="replace")
        clipboard.set_text(text, -1)
        clipboard.store()
    elif mime == "image/png":
        loader = GdkPixbuf.PixbufLoader.new_with_type("png")
        loader.write(payload)
        loader.close()
        pixbuf = loader.get_pixbuf()
        if pixbuf is not None:
            clipboard.set_image(pixbuf)
            clipboard.store()

    # Process pending X11 events so clipboard ownership & store complete cleanly
    while Gtk.events_pending():
        Gtk.main_iteration()
    GLib.timeout_add(150, Gtk.main_quit)
    Gtk.main()


class ClipboardWatchDaemon:
    def __init__(self, peer_ssh: str):
        self.peer_ssh = peer_ssh
        self.clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        self.lock = threading.Lock()
        self.clipboard.connect("owner-change", self.on_owner_change)
        print(f"[lan-clip-sync] Watching clipboard -> SSH peer: {self.peer_ssh}", flush=True)

    def on_owner_change(self, clipboard, event):
        GLib.timeout_add(80, self.read_and_send_clipboard)

    def read_and_send_clipboard(self):
        ok, targets = self.clipboard.wait_for_targets()
        if not ok or not targets:
            return False

        target_names = [t.name() for t in targets]

        # 1. Check for Screenshot / Image first
        if any(t in target_names for t in ("image/png", "image/bmp", "image/jpeg")):
            pixbuf = self.clipboard.wait_for_image()
            if pixbuf is not None:
                ok_png, png_bytes = pixbuf.save_to_bufferv("png", [], [])
                if ok_png and png_bytes:
                    digest = compute_hash("image/png", png_bytes)
                    with self.lock:
                        if digest == read_last_hash():
                            return False
                        write_last_hash(digest)
                    threading.Thread(
                        target=self.send_via_ssh,
                        args=("image/png", png_bytes, digest),
                        daemon=True,
                    ).start()
                    return False

        # 2. Check for UTF-8 Text
        if any("UTF8_STRING" in t or "text/plain" in t or "STRING" in t for t in target_names):
            text = self.clipboard.wait_for_text()
            if text:
                raw = text.encode("utf-8")
                digest = compute_hash("text/plain", raw)
                with self.lock:
                    if digest == read_last_hash():
                        return False
                    write_last_hash(digest)
                threading.Thread(
                    target=self.send_via_ssh,
                    args=("text/plain", raw, digest),
                    daemon=True,
                ).start()

        return False

    def send_via_ssh(self, mime_type: str, payload: bytes, digest: str):
        if len(payload) > MAX_PAYLOAD_BYTES:
            return
        header = json.dumps({
            "mime": mime_type,
            "size": len(payload),
            "sha256": digest,
        }).encode("utf-8")
        packet = struct.pack("!I", len(header)) + header + payload
        try:
            proc = subprocess.run(
                [
                    "ssh",
                    "-o", "BatchMode=yes",
                    "-o", "ConnectTimeout=2",
                    self.peer_ssh,
                    "~/.local/bin/lan-clip-sync.py --apply",
                ],
                input=packet,
                capture_output=True,
                timeout=10,
            )
            if proc.returncode == 0:
                print(f"[lan-clip-sync] Synced {mime_type} ({len(payload)} bytes) -> {self.peer_ssh}", flush=True)
            else:
                err = proc.stderr.decode("utf-8", errors="replace").strip()
                print(f"[lan-clip-sync] SSH apply error ({proc.returncode}): {err}", flush=True)
        except Exception as e:
            print(f"[lan-clip-sync] Peer {self.peer_ssh} unreachable ({e})", flush=True)


if __name__ == "__main__":
    if "--apply" in sys.argv:
        run_apply_mode()
    else:
        peer = os.environ.get("CLIP_PEER_SSH", "")
        if not peer and len(sys.argv) > 1:
            peer = sys.argv[1]
        if not peer:
            print("Usage: lan-clip-sync.py <user@peer-ip> | --apply", file=sys.stderr)
            sys.exit(1)
        daemon = ClipboardWatchDaemon(peer)
        Gtk.main()
