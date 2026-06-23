"""CLI de administración (invite-only: las cuentas se crean aquí).

  python -m app.admin create-tenant --name "EGL" --email tu@email.com --password secreto
  python -m app.admin list
  python -m app.admin set-password --email tu@email.com --password nueva
"""

from __future__ import annotations

import argparse

from sqlalchemy import select

from .bootstrap import create_tenant
from .db import SessionLocal, init_db
from .models import Tenant, User
from .security import hash_password


def main() -> None:
    init_db()
    parser = argparse.ArgumentParser(prog="app.admin")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("create-tenant", help="Crea un workspace + su usuario")
    p.add_argument("--name", required=True)
    p.add_argument("--email", required=True)
    p.add_argument("--password", required=True)

    sub.add_parser("list", help="Lista tenants y usuarios")

    sp = sub.add_parser("set-password", help="Cambia la contraseña de un usuario")
    sp.add_argument("--email", required=True)
    sp.add_argument("--password", required=True)

    args = parser.parse_args()
    with SessionLocal() as db:
        if args.cmd == "create-tenant":
            try:
                t = create_tenant(db, name=args.name, email=args.email, password=args.password)
            except ValueError as err:
                print(f"Error: {err}")
                return
            print(f"✓ Tenant '{t.name}' creado · login: {args.email} · API key: {t.api_key}")
        elif args.cmd == "list":
            for t in db.execute(select(Tenant)).scalars().all():
                emails = ", ".join(u.email for u in t.users) or "—"
                print(f"[{t.id}] {t.name} · {emails} · api_key={t.api_key}")
        elif args.cmd == "set-password":
            user = db.execute(
                select(User).where(User.email == args.email.strip().lower())
            ).scalar_one_or_none()
            if not user:
                print("No existe ese usuario.")
                return
            user.password_hash = hash_password(args.password)
            db.commit()
            print("✓ Contraseña actualizada.")


if __name__ == "__main__":
    main()
