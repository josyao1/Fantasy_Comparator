"""Delivery seam.

Ships on Gmail SMTP -> Verizon's email-to-SMS gateway, which is free and
delivers a real text. Verizon retires that gateway on 2027-03-31, so the
backend is swappable via NOTIFY_BACKEND with no other code change.
"""
from __future__ import annotations

import smtplib
from email.mime.text import MIMEText

import requests

from . import config


def _send_sms(body: str) -> None:
    missing = [k for k, v in {
        "GMAIL_USER": config.GMAIL_USER,
        "GMAIL_APP_PW": config.GMAIL_APP_PW,
        "SMS_TO": config.SMS_TO,
    }.items() if not v]
    if missing:
        raise RuntimeError(f"missing env vars: {', '.join(missing)}")

    msg = MIMEText(body)
    msg["From"] = config.GMAIL_USER
    msg["To"] = config.SMS_TO
    msg["Subject"] = ""          # gateways prepend a non-empty subject
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
        server.login(config.GMAIL_USER, config.GMAIL_APP_PW)
        server.send_message(msg)


def _send_ntfy(body: str) -> None:
    if not config.NTFY_TOPIC:
        raise RuntimeError("NTFY_TOPIC not set")
    r = requests.post(f"https://ntfy.sh/{config.NTFY_TOPIC}",
                      data=body.encode("utf-8"), timeout=20)
    r.raise_for_status()


BACKENDS = {"sms": _send_sms, "ntfy": _send_ntfy}


def send(body: str) -> None:
    backend = BACKENDS.get(config.NOTIFY_BACKEND)
    if backend is None:
        raise RuntimeError(f"unknown NOTIFY_BACKEND: {config.NOTIFY_BACKEND}")
    backend(body)
