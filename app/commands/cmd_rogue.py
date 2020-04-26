from bs4 import BeautifulSoup
import json
import re
import sys
import os
import requests
import pyjq
import time
import smtplib
import ssl

import click

from app import app
from app import cli as app_cli
from app.utils import LogUtils

app = app.App()

slog = LogUtils.get_logger()  # structlog

#####################################################################
# Settings

# cache settings
seconds_between_checks = 60 * 30  # 5 minutes

url = 'https://www.roguefitness.com/the-ohio-bar-cerakote'
jq_statement = ('.. | objects | select(.product_name)' + ' | select(.product_name | test("Chrome") | not )' +
                ' | select(.product_name | test("(Blue|Green|Red|Orange) Shaft"))' +
                ' | select(.isInStock==true) | .product_name')

#####################################################################
# Click Code


def is_help_called():
    return ('--help' in sys.argv) or ('-h' in sys.argv)


@click.group()
def cli():
    """Subcommand for stock checking"""

    pass


@cli.command()
@click.option('--gmail-email',
              required=not is_help_called(),
              default=lambda: os.environ.get('STOCKCHECK_GMAIL_EMAIL', None),
              show_default='env STOCKCHECK_GMAIL_EMAIL',
              type=str,
              help="Gmail Account Email")
@click.option('--gmail-password',
              required=not is_help_called(),
              default=lambda: os.environ.get('STOCKCHECK_GMAIL_PASSWORD'),
              show_default='env STOCKCHECK_GMAIL_PASSWORD',
              type=str,
              help="Gmail Account Password")
@click.option('--email-notification-target',
              required=not is_help_called(),
              default=lambda: os.environ.get('STOCKCHECK_EMAIL_NOTIFICATION_TARGET'),
              show_default='env STOCKCHECK_EMAIL_NOTIFICATION_TARGET',
              type=str,
              help="Email address to notifiy once stock has been found")
@app_cli.pass_context
def barbell(ctx, gmail_email, gmail_password, email_notification_target):
    """This command checks a webpage, parses stock, and then sends an email when found
    """
    result = check_stock()
    slog.info("Checked Stock", result=result)

    message = f"""\
Subject: Stock Check Found

{result}
"""
    send_email(gmail_email, gmail_password, email_notification_target, message)
    slog.info("Sent email", result="SUCCESS")


def check_stock():
    while True:
        req = requests.get(url)
        soup = BeautifulSoup(req.text, "html.parser")

        ele = soup.find("div", class_="product-hero").find_all("script")[1]
        raw = re.findall('RogueColorSwatches\\((.*)\\);', str(ele), re.DOTALL)[0].strip()
        js = json.loads(f"[{raw}]")

        bbb = pyjq.all(jq_statement, js)

        if len(bbb) == 0:
            # Continue through the loop and try again a while later
            time.sleep(seconds_between_checks)
            continue
        else:
            # We've found the item.  Break out of loop and send email
            return json.dumps(bbb, indent=2)


def send_email(gmail_email, gmail_password, email_notification_target, message):

    server = "smtp.gmail.com"
    port = 465  # TLS port
    context = ssl.create_default_context()

    with smtplib.SMTP_SSL(server, port, context=context) as server:
        server.login(gmail_email, gmail_password)
        server.sendmail(gmail_email, email_notification_target, message)
