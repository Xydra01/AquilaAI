#Tools related to sending, editing, or parsing emails.

import os
import inspect
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import smtplib

class EmailSender:
    """Advanced email sender class for full control over email configuration."""
    
    def __init__(self, smtp_server=None, smtp_port=None, from_email=None, 
                 smtp_password=None, use_tls=True):
        """Initialize the email sender with SMTP credentials.
        
        Args:
            smtp_server: SMTP server address (e.g., 'smtp.gmail.com')
            smtp_port: SMTP port number (e.g., 587 for TLS)
            from_email: Sender email address
            smtp_password: SMTP password or app-specific password
            use_tls: Whether to use TLS encryption (default: True)
        """
        # Load credentials from environment variables if not provided
        self.smtp_server = smtp_server or os.getenv('SMTP_SERVER')
        self.smtp_port = smtp_port or int(os.getenv('SMTP_PORT', 587))
        self.from_email = from_email or os.getenv('FROM_EMAIL')
        self.smtp_password = smtp_password or os.getenv('SMTP_PASSWORD')
        self.use_tls = use_tls
        
        # Validate credentials
        if not all([self.smtp_server, self.from_email, self.smtp_password]):
            raise ValueError("SMTP credentials are missing. Please check your .env file.")
    
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
            # Create message container
            msg = MIMEMultipart()
            msg['From'] = self.from_email
            msg['To'] = ', '.join(recipients)
            msg['Subject'] = subject
            
            # Add CC if provided
            if cc:
                msg['Cc'] = ', '.join(cc)
            
            # Set body content
            if html_body:
                msg.attach(MIMEText(html_body, 'html', 'utf-8'))
            elif plain_body:
                msg.attach(MIMEText(plain_body, 'plain', 'utf-8'))
            else:
                raise ValueError("Either html_body or plain_body must be provided.")
            
            # Attach files if provided
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
            
            # Connect to SMTP server and send email
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
        body: The plain text content of the email.
    """
    try:
        # 1. Hallucination-Proof Argument Catching
        # Even if the agent uses the wrong argument name, we catch it here.
        raw_to = kwargs.get('to_addresses') or kwargs.get('to') or kwargs.get('recipients') or kwargs.get('to_address')
        raw_body = kwargs.get('body') or kwargs.get('text') or kwargs.get('plain_body') or kwargs.get('content')
        
        if not raw_to or not raw_body:
            return "❌ Error: Tool failed. You MUST provide 'to_addresses', 'subject', and 'body' arguments."
            
        # 2. Format the recipients into a list
        recipients = [email.strip() for email in raw_to.split(",")]
        
        # 3. Instantiate the class and send!
        sender = EmailSender() 
        
        success = sender.send_email(
            recipients=recipients, 
            subject=subject, 
            plain_body=raw_body
        )
        
        if success:
            return f"✅ Email successfully sent to: {raw_to}"
        else:
            return "❌ Failed to send email. Check the terminal for details."
            
    except Exception as e:
        return f"❌ Error executing email tool: {str(e)}"
    

EMAIL_TOOLS = {
    "send_email_tool": {"func": send_email_tool, "description": inspect.getdoc(send_email_tool)},
}