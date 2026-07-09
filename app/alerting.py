"""
Alerting module – sends notifications via Slack or email when an out‑of‑control event occurs.
"""

import os
import smtplib
from email.mime.text import MIMEText
import requests
import json
from datetime import datetime


def send_slack_alert(measurement):
    """Send a Slack message using a webhook URL."""
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook_url:
        return False
    message = {
        "text": (
            f"🚨 CNC Alert: Out‑of‑control measurement detected!\n"
            f"Diameter: {measurement['diameter']:.4f} mm\n"
            f"Timestamp: {measurement['timestamp']}"
        )
    }
    try:
        response = requests.post(webhook_url, json=message, timeout=5)
        return response.status_code == 200
    except Exception:
        return False


def send_email_alert(measurement):
    """Send an email alert via SMTP."""
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", 587))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASSWORD")
    recipient = os.getenv("ALERT_RECIPIENT")
    if not all([smtp_host, smtp_user, smtp_pass, recipient]):
        return False

    subject = "CNC Out‑of‑Control Alert"
    body = (
        f"Diameter: {measurement['diameter']:.4f} mm\n"
        f"Timestamp: {measurement['timestamp']}\n"
        "Please check the machine."
    )
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = recipient

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, [recipient], msg.as_string())
        return True
    except Exception:
        return False


def notify(measurement):
    """
    Send an alert using the first available method.
    Slack is tried first; if not configured, email is used.
    """
    if send_slack_alert(measurement):
        return
    send_email_alert(measurement)
