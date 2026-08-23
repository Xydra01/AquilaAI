"""Host-side CLI for the Remote Companion pairing flow.

Run on the host machine (where the data lives), e.g.::

    cd agent
    python -m remote.host_cli host-id     # print this host's stable Host ID
    python -m remote.host_cli pair-code   # mint a one-time 6-digit pairing code
    python -m remote.host_cli devices     # list paired devices
    python -m remote.host_cli revoke <token_id>

Pairing codes must be generated here (not over the network) so an open-source
copy of the client cannot pair without physical/host access.
"""
from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    from . import auth

    parser = argparse.ArgumentParser(prog="remote.host_cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("host-id", help="print the stable Host ID")
    p_code = sub.add_parser("pair-code", help="mint a one-time pairing code")
    p_code.add_argument("--ttl", type=float, default=300.0, help="seconds valid (default 300)")
    sub.add_parser("devices", help="list paired devices")
    p_rev = sub.add_parser("revoke", help="revoke a device token")
    p_rev.add_argument("token_id")

    args = parser.parse_args(argv)

    if args.cmd == "host-id":
        print(auth.get_host_id())
        return 0
    if args.cmd == "pair-code":
        host_id = auth.get_host_id()
        code = auth.generate_pairing_code(ttl=args.ttl)
        print(f"Host ID:       {host_id}")
        print(f"Pairing code:  {code}")
        print(f"Valid for:     {int(args.ttl)}s  (one-time use)")
        print("Enter both in the Aquila companion app to pair this device.")
        return 0
    if args.cmd == "devices":
        devices = auth.list_devices()
        if not devices:
            print("No paired devices.")
            return 0
        for d in devices:
            print(
                f"{d.get('token_id', '?')}  {d.get('name', '?'):<24} "
                f"created={d.get('created_at', '')}  last_seen={d.get('last_seen_at', '') or '-'}"
            )
        return 0
    if args.cmd == "revoke":
        ok = auth.revoke_token(args.token_id)
        print("revoked" if ok else "not found")
        return 0 if ok else 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
