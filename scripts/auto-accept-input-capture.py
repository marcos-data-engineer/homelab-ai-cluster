#!/usr/bin/env python3
"""
Assistente visual de login e inicialização:
1. Aprova automaticamente o diálogo 'Capture Input' do Deskflow (libei).
2. Aprova automaticamente a janela de 'Authentication required' do chaveiro (sem senha).
3. No Notebook: garante o bloqueio seguro da tela após abrir o ambiente gráfico.
"""
import time
import os
import subprocess
import gi
gi.require_version("Atspi", "2.0")
from gi.repository import Atspi

ROLES_SWITCH = {Atspi.Role.TOGGLE_BUTTON, Atspi.Role.CHECK_BOX, Atspi.Role.SWITCH}
IS_NOTEBOOK = "notebook" in os.uname().nodename.lower() or os.path.isdir("/mnt/GoogleDrive")


def walk(obj, depth=0):
    yield obj
    if depth > 12:
        return
    try:
        n = obj.get_child_count()
    except Exception:
        return
    for i in range(n):
        try:
            child = obj.get_child_at_index(i)
        except Exception:
            continue
        if child:
            yield from walk(child, depth + 1)


def do_click(obj):
    try:
        iface = obj.get_action_iface()
        if iface and iface.get_n_actions() > 0:
            iface.do_action(0)
            return True
    except Exception:
        pass
    return False


def handle_capture_input(win):
    switch = None
    share = None
    for o in walk(win):
        try:
            role = o.get_role()
            name = (o.get_name() or "").replace("_", "").strip()
        except Exception:
            continue
        if role in ROLES_SWITCH and switch is None:
            switch = o
        if role == Atspi.Role.PUSH_BUTTON and name == "Share":
            share = o
    if switch is not None:
        try:
            if not switch.get_state_set().contains(Atspi.StateType.CHECKED):
                do_click(switch)
                time.sleep(0.5)
        except Exception:
            pass
    if share is not None:
        for _ in range(10):
            try:
                if share.get_state_set().contains(Atspi.StateType.SENSITIVE):
                    break
            except Exception:
                pass
            time.sleep(0.3)
        return do_click(share)
    return False


def handle_keyring_prompt(win):
    unlock_btn = None
    for o in walk(win):
        try:
            role = o.get_role()
            name = (o.get_name() or "").strip()
            if role == Atspi.Role.PUSH_BUTTON and name in ("Unlock", "Desbloquear", "Continue", "Continuar"):
                unlock_btn = o
                break
        except Exception:
            continue
    if unlock_btn is not None:
        return do_click(unlock_btn)
    return False


def scan():
    clicked = False
    try:
        desktop = Atspi.get_desktop(0)
        for i in range(desktop.get_child_count()):
            app = desktop.get_child_at_index(i)
            if not app:
                continue
            for j in range(app.get_child_count()):
                win = app.get_child_at_index(j)
                if not win:
                    continue
                name = (win.get_name() or "").strip()
                if name == "Capture Input":
                    if handle_capture_input(win):
                        print("[auto-assistant] Capture Input aprovado", flush=True)
                        clicked = True
                elif "Authentication required" in name or "Authentication" in name:
                    if handle_keyring_prompt(win):
                        print("[auto-assistant] Keyring Unlock aprovado automaticamente", flush=True)
                        clicked = True
    except Exception:
        pass
    return clicked


# Se for o notebook, agenda o bloqueio de tela com segurança após abrir o Chrome
if IS_NOTEBOOK:
    def lock_notebook():
        time.sleep(4)
        subprocess.run(["loginctl", "lock-session"], check=False)
    import threading
    threading.Thread(target=lock_notebook, daemon=True).start()

while True:
    if scan():
        time.sleep(2)
    time.sleep(0.7)
