import json
import base64
import asyncio
import logging
from io import BytesIO

import qrcode
import qrcode.constants
import resend

from app.core.config import get_settings

# ─────────────────────────────────────────────────────────────────────────────
# Module-level setup
# ─────────────────────────────────────────────────────────────────────────────
logger   = logging.getLogger(__name__)
settings = get_settings()

# Authenticate the Resend client once at import time.
# RESEND_API_KEY is read from your Render environment variables.
resend.api_key = settings.RESEND_API_KEY

# The "from" address must be a domain you have verified in Resend.
# Until you verify a custom domain, Resend lets you send from
# onboarding@resend.dev for testing. For production, set up your
# own domain (e.g. noreply@cyberodyssey.yourdomain.com) in the
# Resend dashboard and update RESEND_FROM_EMAIL in your env vars.
SENDER_FROM = settings.RESEND_FROM_EMAIL


# ─────────────────────────────────────────────────────────────────────────────
# QR-code generation  (unchanged from original)
# ─────────────────────────────────────────────────────────────────────────────
def _build_qr_payload(
    participant_id: str,
    event_id: str,
    participant_name: str,
    team_id: str,
) -> str:
    """
    Returns a JSON string matching the payload shape expected by scanner.html:
        { p_id, e_id, name, t_id }
    """
    return json.dumps({
        "p_id": participant_id,
        "e_id": event_id,
        "name": participant_name,
        "t_id": team_id,
    }, ensure_ascii=False)


def _generate_qr_bytes(payload: str) -> bytes:
    """
    Renders a QR code from *payload* and returns raw PNG bytes.
    ERROR_CORRECT_M gives ~15% recovery — readable even if slightly damaged.
    """
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
# HTML email body builder  (unchanged from original)
# ─────────────────────────────────────────────────────────────────────────────
def _build_html_body(
    participant_name: str,
    event_name: str,
    team_id: str,
) -> tuple[str, str]:
    """
    Returns (plain_text, html_string).
    The HTML uses a data-URI for the QR image so no CID/inline-attachment
    tricks are needed — the image is embedded directly in the HTML string
    and works in every mail client.
    """
    first_name = participant_name.split()[0] if participant_name else participant_name

    plain = (
        f"Hello {first_name},\n\n"
        f"Your registration for {event_name} at Cyber Odyssey 2.0 is confirmed!\n\n"
        f"Your QR Digital ID is attached to this email as a PNG file.\n"
        f"Please present it to our volunteers at the entry desk.\n\n"
        f"Team / Group ID : {team_id}\n\n"
        f"See you at the event!\n"
        f"— Department of CSE (IoT, CS, BT)\n"
        f"  Cyber Odyssey 2.0 Organising Committee"
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Your Digital ID — Cyber Odyssey 2.0</title>
</head>
<body style="margin:0;padding:0;background:#050507;font-family:'Courier New',Courier,monospace;color:#c8ccd8;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#050507;padding:40px 0;">
    <tr>
      <td align="center">
        <table width="560" cellpadding="0" cellspacing="0"
               style="background:#0c0c14;border:1px solid rgba(0,255,204,0.2);
                      border-radius:6px;overflow:hidden;max-width:100%;">
          <tr>
            <td style="background:#050507;padding:24px 32px;
                       border-bottom:1px solid rgba(0,255,204,0.12);text-align:center;">
              <p style="margin:0;font-size:11px;letter-spacing:5px;
                        color:rgba(0,255,204,0.5);text-transform:uppercase;">
                // cyber_odyssey 2.0
              </p>
              <h1 style="margin:8px 0 0;font-size:22px;letter-spacing:4px;
                          color:#00ffcc;text-transform:uppercase;
                          text-shadow:0 0 20px rgba(0,255,204,0.4);">
                Digital ID Issued
              </h1>
            </td>
          </tr>
          <tr>
            <td style="padding:32px 32px 0;">
              <p style="margin:0 0 8px;font-size:15px;color:#fff;">
                Hello <strong style="color:#00ffcc;">{first_name}</strong>,
              </p>
              <p style="margin:0;font-size:13px;line-height:1.7;color:#6b7090;">
                Your registration for
                <strong style="color:#fff;">{event_name}</strong>
                has been confirmed. Your QR Digital ID is attached as a PNG.
                Present it to our volunteers at the entry desk — on your phone
                screen or as a printout.
              </p>
            </td>
          </tr>
          <tr>
            <td style="padding:0 32px 32px;margin-top:24px;">
              <table width="100%" cellpadding="0" cellspacing="0"
                     style="background:#050507;border:1px solid rgba(0,255,204,0.08);
                            border-radius:4px;margin-top:24px;">
                <tr>
                  <td style="padding:14px 20px;border-bottom:1px solid rgba(255,255,255,0.04);">
                    <span style="font-size:10px;letter-spacing:3px;color:#3d4055;
                                 text-transform:uppercase;">Participant</span><br>
                    <strong style="font-size:14px;color:#fff;">{participant_name}</strong>
                  </td>
                </tr>
                <tr>
                  <td style="padding:14px 20px;border-bottom:1px solid rgba(255,255,255,0.04);">
                    <span style="font-size:10px;letter-spacing:3px;color:#3d4055;
                                 text-transform:uppercase;">Event</span><br>
                    <strong style="font-size:14px;color:#00ffcc;">{event_name}</strong>
                  </td>
                </tr>
                <tr>
                  <td style="padding:14px 20px;">
                    <span style="font-size:10px;letter-spacing:3px;color:#3d4055;
                                 text-transform:uppercase;">Team / Group ID</span><br>
                    <strong style="font-size:14px;color:#fff;">{team_id}</strong>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td style="padding:20px 32px 28px;
                       border-top:1px solid rgba(0,255,204,0.08);text-align:center;">
              <p style="margin:0;font-size:11px;letter-spacing:2px;
                        color:#3d4055;text-transform:uppercase;">
                Best of luck — Department of CSE (IoT, CS, BT)<br>
                Cyber Odyssey 2.0 Organising Committee
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

    return plain, html


# ─────────────────────────────────────────────────────────────────────────────
# Resend HTTP send  (replaces the blocked SMTP path entirely)
# ─────────────────────────────────────────────────────────────────────────────
def _resend_send_blocking(
    recipient: str,
    subject: str,
    plain_body: str,
    html_body: str,
    qr_bytes: bytes,
    participant_name: str,
) -> None:
    """
    Sends the email via Resend's HTTP API.
    Resend handles all SMTP relay internally — outbound port 587 is never
    opened from the Render server, so the 'Network is unreachable' error
    that blocked the SMTP path cannot occur here.

    The QR code is sent as an attachment (base64-encoded PNG).
    """
    safe_name  = participant_name.replace(" ", "_").replace("/", "_")
    qr_b64     = base64.b64encode(qr_bytes).decode("utf-8")

    params: resend.Emails.SendParams = {
        "from":    SENDER_FROM,
        "to":      [recipient],
        "subject": subject,
        "text":    plain_body,
        "html":    html_body,
        "attachments": [
            {
                "filename": f"{safe_name}_Digital_ID.png",
                "content":  qr_b64,
            }
        ],
    }

    response = resend.Emails.send(params)
    logger.info("Resend dispatch accepted. Message ID: %s → %s", response.get("id"), recipient)


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
    """
    Generates a QR-code Digital ID and emails it via Resend.
    Drop-in replacement for the old SMTP version — same signature,
    same async interface, same non-fatal error contract.
    """
    resolved_event_id = (
        event_id.strip()
        if event_id.strip()
        else "event_" + event_name.lower().replace(" ", "_")
    )

    # 1. Build QR payload and render PNG bytes
    qr_payload = _build_qr_payload(
        participant_id=participant_id,
        event_id=resolved_event_id,
        participant_name=participant_name,
        team_id=team_id,
    )
    logger.debug("QR payload for %s: %s", participant_email, qr_payload)

    qr_bytes = _generate_qr_bytes(qr_payload)

    # 2. Build email content
    plain_body, html_body = _build_html_body(
        participant_name=participant_name,
        event_name=event_name,
        team_id=team_id,
    )

    subject = f"Your Digital ID — Cyber Odyssey 2.0 | {event_name}"

    # 3. Send via thread pool (resend.Emails.send is synchronous)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        _resend_send_blocking,
        participant_email,
        subject,
        plain_body,
        html_body,
        qr_bytes,
        participant_name,
    )

    logger.info("Digital ID email successfully dispatched to %s", participant_email)