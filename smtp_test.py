import os
from email.message import EmailMessage
import smtplib
from dotenv import load_dotenv

load_dotenv()

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
EMAIL_TO = os.getenv("EMAIL_TO")

print("SMTP_USER:", SMTP_USER)
print("EMAIL_TO:", EMAIL_TO)

msg = EmailMessage()
msg["From"] = SMTP_USER
msg["To"] = EMAIL_TO
msg["Subject"] = "SMTP Test"
msg.set_content("If you see this, the FirstCry monitor email system works!")

with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
    s.starttls()
    s.login(SMTP_USER, SMTP_PASS)
    s.send_message(msg)

print("Email Sent Successfully!")
