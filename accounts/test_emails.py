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

	def test_unknown_account(self):
		self.client.post(reverse('account_reset_password'), {'email': 'nobody@example.com'})
		self.assertIn('Аккаунт не найден', html_of(mail.outbox[0]))

	def test_signup_confirmation(self):
		self.client.post(reverse('account_signup'), {
			'username': 'bob', 'email': 'bob@example.com', 'password1': 'Long-pass-12345', 'password2': 'Long-pass-12345',
			'accept_rules': 'on', 'pd_consent': 'on',
		})
		html = html_of(mail.outbox[0])
		self.assertIn('Подтвердить почту', html)
		self.assertIn('@bob', html)
