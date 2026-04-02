from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .settings import settings


class UpdateService:
    def __init__(self, project_dir: Path) -> None:
        self.project_dir = project_dir
        self.git_path = shutil.which("git")
        self.sudo_path = shutil.which("sudo") or "/usr/bin/sudo"
        self.systemctl_path = shutil.which("systemctl") or "/usr/bin/systemctl"

    def status(self, configured_zip_url: str = "") -> dict[str, Any]:
        zip_url = configured_zip_url.strip() or settings.update_source_zip_url
        git_available = self.git_path is not None and (self.project_dir / ".git").exists()
        payload: dict[str, Any] = {
            "mode": "git" if git_available else ("zip" if zip_url else "none"),
            "project_dir": str(self.project_dir),
            "git_available": git_available,
            "zip_url_configured": bool(zip_url),
            "zip_url": zip_url,
            "can_update": git_available,
        }
        if git_available:
            payload.update(self._git_status())
        else:
            payload.update(
                {
                    "branch": None,
                    "local_commit": None,
                    "remote_commit": None,
                    "update_available": False,
                    "message": "Update per Controller ist nur in einer Git-Installation aktiv.",
                }
            )
        return payload

    def check(self, configured_zip_url: str = "") -> dict[str, Any]:
        return self.status(configured_zip_url=configured_zip_url)

    def apply_git_update(self) -> dict[str, Any]:
        status = self.status()
        if not status.get("git_available"):
            raise RuntimeError("Update per Controller ist nur in einer Git-Installation aktiv.")

        if not self.git_path:
            raise RuntimeError("git ist nicht installiert")

        branch = status.get("branch") or settings.update_git_branch
        venv_pip = self.project_dir / ".venv" / "bin" / "pip"
        pip_cmd = shlex.quote(str(venv_pip if venv_pip.exists() else shutil.which("pip") or "/usr/bin/pip"))
        git_cmd = shlex.quote(self.git_path)
        project_dir = shlex.quote(str(self.project_dir))
        sudo_cmd = shlex.quote(self.sudo_path)
        systemctl_cmd = shlex.quote(self.systemctl_path)
        branch_q = shlex.quote(branch)
        service_name = "onradio-cover.service"
        shell_command = (
            f"cd {project_dir} && "
            f"{git_cmd} fetch origin {branch_q} && "
            f"{git_cmd} pull --ff-only origin {branch_q} && "
            f"{pip_cmd} install -r requirements.txt && "
            f"{sudo_cmd} -n {systemctl_cmd} restart {service_name}"
        )
        subprocess.Popen(  # noqa: S603,S607
            ["/bin/sh", "-lc", f"sleep 1; {shell_command}"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,
            env=os.environ.copy(),
        )
        return {
            "ok": True,
            "message": "Update wird gestartet. Der Dienst wird danach neu gestartet.",
        }

    def _git_status(self) -> dict[str, Any]:
        assert self.git_path is not None
        branch = self._run_git(["rev-parse", "--abbrev-ref", "HEAD"])
        local_commit = self._run_git(["rev-parse", "--short", "HEAD"])
        remote_commit = None
        update_available = False
        message = None
        try:
            remote_line = self._run_git(["ls-remote", "--heads", "origin", branch])
            remote_commit = (remote_line.split()[0][:7] if remote_line else None)
            update_available = bool(remote_commit and remote_commit != local_commit)
            if update_available:
                message = f"Update verfuegbar: {remote_commit}"
            else:
                message = "Bereits aktuell"
        except Exception as exc:  # noqa: BLE001
            message = f"Remote-Pruefung fehlgeschlagen: {exc}"
        return {
            "branch": branch,
            "local_commit": local_commit,
            "remote_commit": remote_commit,
            "update_available": update_available,
            "message": message,
        }

    def _run_git(self, args: list[str]) -> str:
        if not self.git_path:
            raise RuntimeError("git ist nicht installiert")
        completed = subprocess.run(
            [self.git_path, *args],
            cwd=self.project_dir,
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )
        if completed.returncode != 0:
            message = completed.stderr.strip() or completed.stdout.strip() or f"git Fehler {completed.returncode}"
            raise RuntimeError(message)
        return completed.stdout.strip()
