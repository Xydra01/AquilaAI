#Tools related to sending, editing, or parsing emails.

import os
import inspect
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import smtplib
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path.cwd() / ".env")

class EmailSender:
    """Advanced email sender class for full control over email configuration."""
    
    def __init__(self, smtp_server=None, smtp_port=None, from_email=None, 
                 smtp_password=None, use_tls=True):
        """Initialize the email sender with SMTP credentials."""
        
        # Load credentials from environment variables
        self.smtp_server = smtp_server or os.getenv('SMTP_SERVER')
        self.smtp_port = smtp_port or int(os.getenv('SMTP_PORT', 587))
        
        
        self.from_email = from_email or os.getenv('SMTP_USER') or os.getenv('FROM_EMAIL') 
        
        self.smtp_password = smtp_password or os.getenv('SMTP_PASSWORD')
        
        
        env_tls = os.getenv('SMTP_USE_TLS', 'true').lower() == 'true'
        self.use_tls = use_tls if use_tls is not None else env_tls
        
        
        if not all([self.smtp_server, self.from_email, self.smtp_password]):
            raise ValueError(f"SMTP credentials are missing. Server: {bool(self.smtp_server)}, User: {bool(self.from_email)}, Pass: {bool(self.smtp_password)}")
    
    def send_email(self, recipients, subject, html_body=None, plain_body=None, 
             cc=None, attachments=None):
        """Send an email with optional attachments and formatting.
        
        Args:
            recipients: List of recipient email addresses
            subject: Email subject line
            html_body: Optional HTML formatted email body
            plain_body: Optional plain text fallback body
            cc: Optional list of CC recipient emails
            attachments: Optional list of file paths to attach
            
        Returns:
            bool: True if email sent successfully, False otherwise
        """
        try:
            #Message container
            msg = MIMEMultipart()
            msg['From'] = self.from_email
            msg['To'] = ', '.join(recipients)
            msg['Subject'] = subject
            
            # Add CC
            if cc:
                msg['Cc'] = ', '.join(cc)
            
            # Set body
            if html_body:
                msg.attach(MIMEText(html_body, 'html', 'utf-8'))
            elif plain_body:
                msg.attach(MIMEText(plain_body, 'plain', 'utf-8'))
            else:
                raise ValueError("Either html_body or plain_body must be provided.")
            
            # Attach files
            if attachments:
                for file_path in attachments:
                    with open(file_path, 'rb') as attachment:
                        part = MIMEBase('application', 'octet-stream')
                        part.set_payload(attachment.read())
                    encoders.encode_base64(part)
                    part.add_header(
                        'Content-Disposition',
                        f'attachment; filename= {os.path.basename(file_path)}'
                    )
                    msg.attach(part)
            
            if self.use_tls:
                server = smtplib.SMTP(self.smtp_server, self.smtp_port)
                server.starttls()
                server.login(self.from_email, self.smtp_password)
            else:
                server = smtplib.SMTP_SSL(self.smtp_server, self.smtp_port)
            
            server.send_message(msg)
            server.quit()
            return True
            
        except Exception as e:
            print(f"Failed to send email: {str(e)}")
            return False
    
    def disconnect(self):
        """Disconnect from SMTP server."""
        try:
            if hasattr(self, 'server'):
                self.server.quit()
        except Exception:
            pass

def send_email_tool(subject: str, **kwargs) -> str:
    """
    Sends an email using the SMTP credentials in your .env file.
    
    Args:
        subject: The subject line of the email.
        to_addresses: A comma-separated string of recipient emails (e.g., "user1@test.com, user2@test.com").
        body: The content of the email.
        cc: (Optional) A comma-separated string of CC recipient emails.
        attachments: (Optional) A comma-separated string of file paths to attach.
        is_html: (Optional) Set to 'true' if the body contains HTML formatting.
    """
    try:
        raw_to = kwargs.get('to_addresses') or kwargs.get('to') or kwargs.get('recipients') or kwargs.get('to_address')
        raw_body = kwargs.get('body') or kwargs.get('text') or kwargs.get('plain_body') or kwargs.get('content')
        raw_cc = kwargs.get('cc') or kwargs.get('cc_addresses')
        raw_attachments = kwargs.get('attachments') or kwargs.get('files')
        
        
        is_html = str(kwargs.get('is_html', 'false')).lower() == 'true'
        
        if not raw_to or not raw_body:
            return "❌ Error: Tool failed. You MUST provide 'to_addresses', 'subject', and 'body' arguments."
            
        
        recipients = [email.strip() for email in raw_to.split(",")]
        cc_list = [email.strip() for email in raw_cc.split(",")] if raw_cc else None
        attachment_list = [path.strip() for path in raw_attachments.split(",")] if raw_attachments else None
        
       
        sender = EmailSender() 
        
        
        html_body = raw_body if is_html else None
        plain_body = raw_body if not is_html else None
        
        
        success = sender.send_email(
            recipients=recipients, 
            subject=subject, 
            plain_body=plain_body,
            html_body=html_body,
            cc=cc_list,
            attachments=attachment_list
        )
        
        if success:
            msg = f"✅ Email successfully sent to: {raw_to}"
            if cc_list: msg += f" (CC: {raw_cc})"
            if attachment_list: msg += f" with {len(attachment_list)} attachment(s)."
            return msg
        else:
            return "❌ Failed to send email. Check the terminal for details."
            
    except Exception as e:
        return f"❌ Error executing email tool: {str(e)}"
    

EMAIL_TOOLS = {
    "send_email_tool": {"func": send_email_tool, "description": inspect.getdoc(send_email_tool)},
}