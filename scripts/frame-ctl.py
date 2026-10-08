#!/usr/bin/env python3
"""Control the Samsung Music Frame (or any Cast device) locally, no account needed.

Connects straight to the device IP (the Music Frame's mDNS is unreliable).

    frame-ctl.py status
    frame-ctl.py vol 30        # absolute, percent
    frame-ctl.py vol +5        # relative
    frame-ctl.py mute | unmute

Host defaults to $CAST_HOST or the first entry of $CAST_KNOWN_HOSTS.
Playback (play/stop) is left to the onradio app: stopping the cast session
from here would just make its watchdog re-cast.
"""
import argparse
import os
import sys

import pychromecast

DEFAULT_HOST = os.environ.get("CAST_HOST") or (
    os.environ.get("CAST_KNOWN_HOSTS", "192.168.42.201").split(",")[0].strip()
)


def connect(host: str) -> pychromecast.Chromecast:
    cast = pychromecast.get_chromecast_from_host((host, 8009, None, None, None))
    try:
        cast.wait(timeout=10)
    except pychromecast.error.RequestTimeout:
        raise SystemExit(f"{host}:8009 not reachable (device off or asleep?)")
    if not cast.status:
        raise SystemExit(f"no status from {host}:8009")
    return cast


def print_status(cast: pychromecast.Chromecast) -> None:
    st = cast.status
    mc = cast.media_controller.status
    print(f"device : {cast.cast_info.friendly_name or cast.cast_info.host}")
    print(f"app    : {st.display_name or '-'}")
    print(f"volume : {round(st.volume_level * 100)}%{' (muted)' if st.volume_muted else ''}")
    print(f"player : {mc.player_state if mc else '-'}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--host", default=DEFAULT_HOST)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    v = sub.add_parser("vol")
    v.add_argument("value", help="0-100, or +N / -N")
    sub.add_parser("mute")
    sub.add_parser("unmute")
    args = p.parse_args()

    cast = connect(args.host)
    try:
        if args.cmd == "vol":
            raw = args.value
            current = round(cast.status.volume_level * 100)
            target = current + int(raw) if raw[0] in "+-" else int(raw)
            target = max(0, min(100, target))
            cast.set_volume(target / 100)
            print(f"volume {current}% -> {target}%")
        elif args.cmd in ("mute", "unmute"):
            cast.set_volume_muted(args.cmd == "mute")
            print(args.cmd + "d")
        else:
            print_status(cast)
    finally:
        cast.disconnect(timeout=5)
    return 0


if __name__ == "__main__":
    sys.exit(main())
