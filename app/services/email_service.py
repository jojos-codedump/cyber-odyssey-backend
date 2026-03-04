import json
import smtplib
import asyncio
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from io import BytesIO
from functools import partial

import qrcode
import qrcode.constants

from app.core.config import get_settings

# ─────────────────────────────────────────────────────────────────────────────
# Module-level setup
# ─────────────────────────────────────────────────────────────────────────────
logger   = logging.getLogger(__name__)
settings = get_settings()

SMTP_SERVER     = settings.SMTP_SERVER.strip()
SMTP_PORT       = int(settings.SMTP_PORT)
SENDER_EMAIL    = settings.SENDER_EMAIL.strip()
SENDER_PASSWORD = settings.SENDER_PASSWORD.strip()

# How many times to retry a failed SMTP send before giving up
MAX_RETRIES = 2


# ─────────────────────────────────────────────────────────────────────────────
# QR-code generation
# ─────────────────────────────────────────────────────────────────────────────
def _build_qr_payload(
    participant_id: str,
    event_id: str,
    participant_name: str,
    team_id: str,
) -> str:
    """
    Returns a JSON string that matches the payload shape expected by
    scanner.html:  { p_id, e_id, name, t_id }

    Using JSON (rather than a plain delimited string) means the scanner
    can extract fields by name and is resilient to names that contain
    the old pipe-delimiter character.
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
    Uses ERROR_CORRECT_M (≈15 % recovery) so the code is still readable
    if printed small or slightly damaged.
    """
    qr = qrcode.QRCode(
        version=None,                               # auto-size
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
# Email assembly
# ─────────────────────────────────────────────────────────────────────────────
def _build_email(
    participant_email: str,
    participant_name: str,
    event_name: str,
    team_id: str,
    qr_bytes: bytes,
) -> MIMEMultipart:
    """
    Assembles a multipart/alternative email (plain-text + HTML) with the
    QR code embedded inline in the HTML body AND attached as a PNG file.
    This covers mail clients that block inline images (they still get the
    attachment) and clients that can't render HTML (they get the plain text).
    """
    first_name = participant_name.split()[0] if participant_name else participant_name

    # ── Plain-text fallback ──────────────────────────────────────────────────
    plain_body = (
        f"Hello {first_name},\n\n"
        f"Your registration for {event_name} at Cyber Odyssey 2.0 is confirmed!\n\n"
        f"Attached to this email is your official Digital ID (QR Code).\n"
        f"Please present it to our volunteers at the entry desk — "
        f"either on your phone screen or as a printout.\n\n"
        f"Team / Group ID : {team_id}\n\n"
        f"See you at the event!\n"
        f"— Department of CSE (IoT, CS, BT)\n"
        f"  Cyber Odyssey 2.0 Organising Committee"
    )

    # ── HTML body (QR embedded inline via CID reference) ────────────────────
    html_body = f"""<!DOCTYPE html>
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

          <!-- Header -->
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

          <!-- Greeting -->
          <tr>
            <td style="padding:32px 32px 0;">
              <p style="margin:0 0 8px;font-size:15px;color:#fff;">
                Hello <strong style="color:#00ffcc;">{first_name}</strong>,
              </p>
              <p style="margin:0;font-size:13px;line-height:1.7;color:#6b7090;">
                Your registration for
                <strong style="color:#fff;">{event_name}</strong>
                has been confirmed. Below is your official QR-based Digital ID.
                Present it to our volunteers at the entry desk — on your phone
                screen or as a printout.
              </p>
            </td>
          </tr>

          <!-- QR code -->
          <tr>
            <td align="center" style="padding:32px;">
              <div style="display:inline-block;padding:16px;
                          background:#fff;border-radius:4px;
                          box-shadow:0 0 30px rgba(0,255,204,0.15);">
                <img src="cid:qr_code_image"
                     alt="Your QR Digital ID"
                     width="200" height="200"
                     style="display:block;border:0;">
              </div>
            </td>
          </tr>

          <!-- Details row -->
          <tr>
            <td style="padding:0 32px 32px;">
              <table width="100%" cellpadding="0" cellspacing="0"
                     style="background:#050507;border:1px solid rgba(0,255,204,0.08);
                            border-radius:4px;">
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

          <!-- Footer -->
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

    # ── Assemble MIME structure ──────────────────────────────────────────────
    # outer: mixed  (carries the attachment)
    # └─ inner: alternative (plain + html)
    #    └─ related (html + inline image)
    outer = MIMEMultipart("mixed")
    outer["Subject"] = f"Your Digital ID — Cyber Odyssey 2.0 | {event_name}"
    outer["From"]    = f"Cyber Odyssey 2.0 <{SENDER_EMAIL}>"
    outer["To"]      = participant_email

    # alternative wrapper
    alternative = MIMEMultipart("alternative")

    # plain text
    alternative.attach(MIMEText(plain_body, "plain", "utf-8"))

    # related: binds HTML + inline image together
    related = MIMEMultipart("related")
    related.attach(MIMEText(html_body, "html", "utf-8"))

    # inline QR (referenced in HTML via cid:qr_code_image)
    inline_qr = MIMEImage(qr_bytes, _subtype="png")
    inline_qr.add_header("Content-ID", "<qr_code_image>")
    inline_qr.add_header("Content-Disposition", "inline", filename="digital_id.png")
    related.attach(inline_qr)

    alternative.attach(related)
    outer.attach(alternative)

    # standalone attachment (for clients that strip inline images)
    attachment = MIMEImage(qr_bytes, _subtype="png")
    safe_name   = participant_name.replace(" ", "_").replace("/", "_")
    attachment.add_header(
        "Content-Disposition", "attachment",
        filename=f"{safe_name}_Digital_ID.png"
    )
    outer.attach(attachment)

    return outer


# ─────────────────────────────────────────────────────────────────────────────
# SMTP send (synchronous — runs in a thread pool so it doesn't block the
# FastAPI event loop)
# ─────────────────────────────────────────────────────────────────────────────
def _smtp_send_blocking(msg: MIMEMultipart, recipient: str) -> None:
    """
    Synchronous SMTP send with retry logic.
    Raises on final failure so the caller can log/handle it.
    """
    last_exc: Exception | None = None

    for attempt in range(1, MAX_RETRIES + 2):   # attempts: 1, 2, 3
        try:
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=15) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(SENDER_EMAIL, SENDER_PASSWORD)
                server.sendmail(SENDER_EMAIL, [recipient], msg.as_string())

            logger.info("Email delivered to %s (attempt %d)", recipient, attempt)
            return   # success

        except smtplib.SMTPAuthenticationError as exc:
            # Wrong credentials — retrying won't help
            logger.error("SMTP authentication failed. Check SENDER_EMAIL / SENDER_PASSWORD.")
            raise exc

        except smtplib.SMTPRecipientsRefused as exc:
            # Invalid recipient address — retrying won't help
            logger.error("Recipient address refused by SMTP server: %s", recipient)
            raise exc

        except (smtplib.SMTPException, OSError, TimeoutError) as exc:
            last_exc = exc
            logger.warning(
                "SMTP send failed on attempt %d/%d for %s: %s",
                attempt, MAX_RETRIES + 1, recipient, exc
            )
            if attempt <= MAX_RETRIES:
                # Brief back-off before retry (blocking is fine — we're in a thread)
                import time
                time.sleep(2 * attempt)

    raise RuntimeError(
        f"Email to {recipient} failed after {MAX_RETRIES + 1} attempts. "
        f"Last error: {last_exc}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Public async interface (called by routes.py with `await`)
# ─────────────────────────────────────────────────────────────────────────────
async def send_qr_email(
    participant_email: str,
    participant_name: str,
    team_id: str,
    event_name: str,
    participant_id: str,          # ← Bug A fix: added missing parameter
    event_id: str = "",           # raw Firestore event_id e.g. "event_codeshield"
) -> None:
    """
    Generates a QR-code Digital ID and emails it to the participant.

    Must be called with `await` from an async context (FastAPI route handler).
    The blocking SMTP work is offloaded to a thread-pool executor so it never
    stalls the event loop.

    Raises on unrecoverable errors (auth failure, bad recipient).
    Logs and re-raises on transient errors after MAX_RETRIES attempts.
    """

    # ── 1. Derive event_id if caller only supplied event_name ────────────────
    # Prefer the explicit event_id field; fall back to deriving it from name.
    resolved_event_id = (
        event_id.strip()
        if event_id.strip()
        else "event_" + event_name.lower().replace(" ", "_")
    )

    # ── 2. Build QR payload (JSON, matches scanner.html parser) ─────────────
    qr_payload = _build_qr_payload(
        participant_id=participant_id,
        event_id=resolved_event_id,
        participant_name=participant_name,
        team_id=team_id,
    )
    logger.debug("QR payload for %s: %s", participant_email, qr_payload)

    # ── 3. Generate QR code bytes (CPU work — fine on the event loop) ────────
    qr_bytes = _generate_qr_bytes(qr_payload)

    # ── 4. Assemble email ────────────────────────────────────────────────────
    msg = _build_email(
        participant_email=participant_email,
        participant_name=participant_name,
        event_name=event_name,
        team_id=team_id,
        qr_bytes=qr_bytes,
    )

    # ── 5. Send via thread pool (smtplib is synchronous/blocking) ────────────
    # Bug B fix: the original code called `send_qr_email` without `await`,
    # which created a coroutine that was immediately discarded — nothing was
    # ever sent.  By offloading to run_in_executor we remain properly async.
    loop = asyncio.get_event_loop()
    send_fn = partial(_smtp_send_blocking, msg, participant_email)
    await loop.run_in_executor(None, send_fn)

    logger.info("Digital ID email successfully dispatched to %s", participant_email)