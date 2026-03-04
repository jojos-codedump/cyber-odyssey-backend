import json
import base64
import asyncio
import logging
from io import BytesIO

import qrcode
import qrcode.constants
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import (
    Mail, Attachment, FileContent, FileName,
    FileType, Disposition, To
)

from app.core.config import get_settings

# ─────────────────────────────────────────────────────────────────────────────
# Module-level setup
# ─────────────────────────────────────────────────────────────────────────────
logger   = logging.getLogger(__name__)
settings = get_settings()

# Must match exactly what you verified in SendGrid → Single Sender Verification.
SENDER_FROM      = settings.SENDGRID_FROM_EMAIL
SENDER_FROM_NAME = "Cyber Odyssey 2.0"


# ─────────────────────────────────────────────────────────────────────────────
# QR-code generation  (unchanged)
# ─────────────────────────────────────────────────────────────────────────────
def _build_qr_payload(participant_id, event_id, participant_name, team_id):
    return json.dumps({
        "p_id": participant_id,
        "e_id": event_id,
        "name": participant_name,
        "t_id": team_id,
    }, ensure_ascii=False)


def _generate_qr_bytes(payload: str) -> bytes:
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# Email content builder
# ─────────────────────────────────────────────────────────────────────────────
def _build_email_content(participant_name, event_name, team_id):
    """Returns (plain_text, html_string)."""
    first_name = participant_name.split()[0] if participant_name else participant_name

    plain = (
        f"Hello {first_name},\n\n"
        f"Your registration for {event_name} at Cyber Odyssey 2.0 is confirmed!\n\n"
        f"Your QR Digital ID is attached to this email as a PNG file.\n"
        f"Present it to our volunteers at the entry desk.\n\n"
        f"Team / Group ID : {team_id}\n\n"
        f"See you at the event!\n"
        f"— Department of CSE (IoT, CS, BT)\n"
        f"  Cyber Odyssey 2.0 Organising Committee"
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Your Digital ID — Cyber Odyssey 2.0</title></head>
<body style="margin:0;padding:0;background:#050507;font-family:'Courier New',Courier,monospace;color:#c8ccd8;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#050507;padding:40px 0;">
    <tr><td align="center">
      <table width="560" cellpadding="0" cellspacing="0"
             style="background:#0c0c14;border:1px solid rgba(0,255,204,0.2);border-radius:6px;overflow:hidden;max-width:100%;">
        <tr>
          <td style="background:#050507;padding:24px 32px;border-bottom:1px solid rgba(0,255,204,0.12);text-align:center;">
            <p style="margin:0;font-size:11px;letter-spacing:5px;color:rgba(0,255,204,0.5);text-transform:uppercase;">// cyber_odyssey 2.0</p>
            <h1 style="margin:8px 0 0;font-size:22px;letter-spacing:4px;color:#00ffcc;text-transform:uppercase;">Digital ID Issued</h1>
          </td>
        </tr>
        <tr>
          <td style="padding:32px 32px 0;">
            <p style="margin:0 0 8px;font-size:15px;color:#fff;">Hello <strong style="color:#00ffcc;">{first_name}</strong>,</p>
            <p style="margin:0;font-size:13px;line-height:1.7;color:#6b7090;">
              Your registration for <strong style="color:#fff;">{event_name}</strong> is confirmed.
              Your QR Digital ID is attached as a PNG. Present it at the entry desk.
            </p>
          </td>
        </tr>
        <tr>
          <td style="padding:24px 32px 32px;">
            <table width="100%" cellpadding="0" cellspacing="0"
                   style="background:#050507;border:1px solid rgba(0,255,204,0.08);border-radius:4px;">
              <tr><td style="padding:14px 20px;border-bottom:1px solid rgba(255,255,255,0.04);">
                <span style="font-size:10px;letter-spacing:3px;color:#3d4055;text-transform:uppercase;">Participant</span><br>
                <strong style="font-size:14px;color:#fff;">{participant_name}</strong>
              </td></tr>
              <tr><td style="padding:14px 20px;border-bottom:1px solid rgba(255,255,255,0.04);">
                <span style="font-size:10px;letter-spacing:3px;color:#3d4055;text-transform:uppercase;">Event</span><br>
                <strong style="font-size:14px;color:#00ffcc;">{event_name}</strong>
              </td></tr>
              <tr><td style="padding:14px 20px;">
                <span style="font-size:10px;letter-spacing:3px;color:#3d4055;text-transform:uppercase;">Team / Group ID</span><br>
                <strong style="font-size:14px;color:#fff;">{team_id}</strong>
              </td></tr>
            </table>
          </td>
        </tr>
        <tr>
          <td style="padding:20px 32px 28px;border-top:1px solid rgba(0,255,204,0.08);text-align:center;">
            <p style="margin:0;font-size:11px;letter-spacing:2px;color:#3d4055;text-transform:uppercase;">
              Best of luck — Department of CSE (IoT, CS, BT)<br>Cyber Odyssey 2.0 Organising Committee
            </p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""

    return plain, html


# ─────────────────────────────────────────────────────────────────────────────
# SendGrid HTTP send (blocking — runs in thread pool)
# ─────────────────────────────────────────────────────────────────────────────
def _sendgrid_send_blocking(recipient, subject, plain_body, html_body, qr_bytes, participant_name):
    """
    Sends via SendGrid HTTP API.
    No SMTP port required — works on Render free tier.
    """
    message = Mail(
        from_email=(SENDER_FROM, SENDER_FROM_NAME),
        to_emails=To(recipient),
        subject=subject,
        plain_text_content=plain_body,
        html_content=html_body,
    )

    safe_name = participant_name.replace(" ", "_").replace("/", "_")
    qr_b64    = base64.b64encode(qr_bytes).decode("utf-8")

    attachment = Attachment(
        file_content=FileContent(qr_b64),
        file_name=FileName(f"{safe_name}_Digital_ID.png"),
        file_type=FileType("image/png"),
        disposition=Disposition("attachment"),
    )
    message.attachment = attachment

    sg       = SendGridAPIClient(settings.SENDGRID_API_KEY)
    response = sg.send(message)

    if response.status_code not in (200, 202):
        raise RuntimeError(
            f"SendGrid rejected the email. "
            f"Status: {response.status_code} | Body: {response.body}"
        )

    logger.info("SendGrid accepted. Status %s → %s", response.status_code, recipient)


# ─────────────────────────────────────────────────────────────────────────────
# Public async interface  (signature unchanged — routes.py needs no edits)
# ─────────────────────────────────────────────────────────────────────────────
async def send_qr_email(
    participant_email: str,
    participant_name: str,
    team_id: str,
    event_name: str,
    participant_id: str,
    event_id: str = "",
) -> None:
    resolved_event_id = (
        event_id.strip() if event_id.strip()
        else "event_" + event_name.lower().replace(" ", "_")
    )

    qr_payload = _build_qr_payload(
        participant_id=participant_id,
        event_id=resolved_event_id,
        participant_name=participant_name,
        team_id=team_id,
    )

    qr_bytes              = _generate_qr_bytes(qr_payload)
    plain_body, html_body = _build_email_content(participant_name, event_name, team_id)
    subject               = f"Your Digital ID — Cyber Odyssey 2.0 | {event_name}"

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        _sendgrid_send_blocking,
        participant_email, subject,
        plain_body, html_body,
        qr_bytes, participant_name,
    )

    logger.info("Digital ID dispatched to %s", participant_email)