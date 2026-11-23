from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from azzb.testing import ACTIVE

from .models import Poll
from .services import publish_post, vote

User = get_user_model()
HX = {'HTTP_HX_REQUEST': 'true'}


def make(name):
	return User.objects.create_user(name, f'{name}@example.com', **ACTIVE)


class PollTests(TestCase):
	@classmethod
	def setUpTestData(cls):
		cls.ann, cls.bob, cls.cat = make('ann'), make('bob'), make('cat')
		cls.post = publish_post(cls.ann.profile, 'Чай или кофе?', poll_options=['Чай', 'Кофе', ''], poll_duration='24')
		cls.tea, cls.coffee = cls.post.poll.options.all()

	def page(self, user):
		self.client.force_login(user)
		return self.client.get(reverse('post', args=[self.post.pk]))

	def test_results_hidden_until_vote(self):
		vote(self.post, self.cat.profile, self.tea.pk)
		response = self.page(self.bob)
		self.assertContains(response, 'poll-choice', count=2)
		self.assertNotContains(response, 'poll-percent')
		response = self.client.post(reverse('post-vote', args=[self.post.pk]), {'option': self.coffee.pk}, **HX)
		self.assertContains(response, '<b class="poll-percent">50%</b>', count=2)
		self.assertContains(response, 'ваш выбор')
		self.assertContains(self.page(self.ann), '2 голоса')

	def test_one_vote_no_author_vote_and_closed(self):
		vote(self.post, self.bob.profile, self.tea.pk)
		with self.assertRaises(ValidationError):
			vote(self.post, self.bob.profile, self.coffee.pk)
		with self.assertRaises(ValidationError):
			vote(self.post, self.ann.profile, self.tea.pk)
		Poll.objects.filter(pk=self.post.poll.pk).update(ends_at=timezone.now() - timedelta(minutes=1))
		self.post.poll.refresh_from_db()
		with self.assertRaises(ValidationError):
			vote(self.post, self.cat.profile, self.tea.pk)
		response = self.page(self.cat)
		self.assertContains(response, 'Опрос завершён')
		self.assertContains(response, '100%')
