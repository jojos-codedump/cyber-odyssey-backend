import smtplib
from email.message import EmailMessage
import qrcode
from io import BytesIO
import logging

# 1. Import our centralized settings manager
from app.core.config import get_settings

logger = logging.getLogger(__name__)

# 2. Load the settings
settings = get_settings()

# 3. Assign the variables directly from Pydantic
SMTP_SERVER = settings.SMTP_SERVER.strip()
SMTP_PORT = settings.SMTP_PORT
SENDER_EMAIL = settings.SENDER_EMAIL.strip()
SENDER_PASSWORD = settings.SENDER_PASSWORD.strip()

def generate_qr_code_bytes(data_string: str) -> bytes:
    """
    Generates a QR code from a string and returns it as a byte array.
    This avoids having to save the image to the server's disk.
    """
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(data_string)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    
    # Save image to an in-memory bytes buffer
    img_byte_arr = BytesIO()
    img.save(img_byte_arr, format='PNG')
    return img_byte_arr.getvalue()

async def send_qr_email(participant_email: str, participant_name: str, team_id: str, event_name: str):
    """
    Constructs and sends the Digital ID email with the QR code attached.
    Designed to be called asynchronously by the FastAPI router.
    """
    try:
        # 1. Format the data string exactly as required by the specification
        qr_data_string = f"{participant_name} | {team_id} | {event_name}"
        
        # 2. Generate the QR code bytes
        qr_bytes = generate_qr_code_bytes(qr_data_string)
        
        # 3. Construct the email message
        msg = EmailMessage()
        msg['Subject'] = f"Your Digital ID for Cyber Odyssey 2.0 - {event_name}"
        msg['From'] = SENDER_EMAIL
        msg['To'] = participant_email
        
        email_body = (
            f"Hello {participant_name},\n\n"
            f"Welcome to Cyber Odyssey 2.0! Your registration for {event_name} is confirmed.\n\n"
            f"Attached to this email is your official Digital ID (QR Code).\n"
            f"Please have this QR code ready on your phone to be scanned by our volunteers at the entry desk.\n\n"
            f"Team ID: {team_id}\n\n"
            f"Best of luck,\n"
            f"The Department of CSE (IoT, CS, BT)"
        )
        msg.set_content(email_body)
        
        # 4. Attach the generated QR code
        msg.add_attachment(
            qr_bytes, 
            maintype='image', 
            subtype='png', 
            filename=f"{participant_name.replace(' ', '_')}_Digital_ID.png"
        )
        
        # 5. Connect to SMTP server and send
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()  # Secure the connection
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
            
        logger.info(f"Successfully sent Digital ID email to {participant_email}")
        
    except Exception as e:
        logger.error(f"Failed to send email to {participant_email}. Error: {e}")