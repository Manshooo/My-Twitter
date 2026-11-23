from allauth.account.models import EmailAddress
from allauth.usersessions.models import UserSession
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from azzb.models import ActivityRecord
from azzb.testing import ACTIVE

Action = ActivityRecord.Action
IPHONE = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1'
WINDOWS = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 YaBrowser/24.10.0.0 Safari/537.36'
def make(name):
	user = get_user_model().objects.create_user(name, f'{name}@example.com', 'pass-12345', **ACTIVE)
	EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)
	return user


class SecurityEventsTests(TestCase):
	def setUp(self):
		self.ann = make('ann')

	def login(self, agent, password='pass-12345', client=None):
		client = client or Client()
		client.post(reverse('account_login'), {'login': 'ann', 'password': password}, headers={'User-Agent': agent})
		return client

	def test_failed_login_recorded_only_for_existing_account(self):
		self.login(IPHONE, password='wrong')
		self.assertTrue(ActivityRecord.objects.filter(user=self.ann, action=Action.LOGIN_FAILED).exists())
		Client().post(reverse('account_login'), {'login': 'nobody-here', 'password': 'x'})
		self.assertEqual(ActivityRecord.objects.filter(action=Action.LOGIN_FAILED).count(), 1)


class SessionsTests(TestCase):
	def setUp(self):
		self.ann = make('ann')
		self.phone, self.laptop = Client(headers={'User-Agent': IPHONE}), Client(headers={'User-Agent': WINDOWS})
		for client in (self.phone, self.laptop):
			client.post(reverse('account_login'), {'login': 'ann', 'password': 'pass-12345'})

	def test_lists_devices_and_ends_other(self):
		page = self.laptop.get(reverse('account-settings'))
		sessions = page.context['sessions']
		self.assertEqual([s.title for s in sessions], ['Яндекс Браузер, Windows', 'Safari, iPhone'])
		self.assertTrue(sessions[0].current)
		self.assertContains(page, 'Это устройство')
		self.laptop.post(reverse('account-sessions-end'), {'session': 'others'})
		self.assertEqual(UserSession.objects.filter(user=self.ann).count(), 1)
		self.assertEqual(self.phone.get(reverse('account-settings')).status_code, 302, 'телефон разлогинен')
		self.assertEqual(self.laptop.get(reverse('account-settings')).status_code, 200)
		self.assertTrue(ActivityRecord.objects.filter(user=self.ann, action=Action.SESSIONS_END).exists())

	def test_cannot_end_someone_elses_session(self):
		bob = Client()
		make('bob')
		bob.post(reverse('account_login'), {'login': 'bob', 'password': 'pass-12345'})
		phone_session = UserSession.objects.get(user=self.ann, user_agent=IPHONE)
		bob.post(reverse('account-sessions-end'), {'session': phone_session.pk})
		self.assertTrue(UserSession.objects.filter(pk=phone_session.pk).exists())
