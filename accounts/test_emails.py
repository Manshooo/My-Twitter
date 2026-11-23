from django.core import mail
from django.test import TestCase
from django.urls import reverse

from .test_devices import make


def html_of(message):
	return next(body for body, kind in message.alternatives if kind == 'text/html')


class EmailLayoutTests(TestCase):
	def test_password_reset_has_html_with_logo_and_button(self):
		make('ann')
		self.client.post(reverse('account_reset_password'), {'email': 'ann@example.com'})
		message = mail.outbox[0]
		html = html_of(message)
		self.assertIn('http://testserver/static/images/email-logo.png', html)
		self.assertIn('Задать новый пароль', html)
		link = next(line for line in message.body.splitlines() if line.startswith('http'))
		self.assertIn(f'href="{link}"', html)
		self.assertIn('@ann', message.body)
