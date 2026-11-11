from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.account import collect_user_data, erase_account
from notifications.models import Notification
from notifications.services import unread_count

from .models import Poll, PollVote
from .services import delete_post, publish_post, purge_posts, toggle_repost, vote
from .models import Post

User = get_user_model()
HX = {'HTTP_HX_REQUEST': 'true'}


def make(name):
	return User.objects.create_user(name, f'{name}@example.com', 'pass-12345')


class PollTests(TestCase):
	def setUp(self):
		self.ann, self.bob, self.cat = make('ann'), make('bob'), make('cat')
		self.post = publish_post(self.ann.profile, 'Чай или кофе?', poll_options=['Чай', 'Кофе', ''], poll_duration='24')
		self.tea, self.coffee = self.post.poll.options.all()

	def page(self, user):
		self.client.force_login(user)
		return self.client.get(reverse('post', args=[self.post.pk]))

	def test_validation(self):
		bad = [
			dict(poll_options=['Один'], poll_duration='24'),
			dict(poll_options=['А', 'а'], poll_duration='24'),
			dict(poll_options=['А', 'Б'], poll_duration='5'),
			dict(poll_options=['А', 'Б', 'В', 'Г', 'Д'], poll_duration='24'),
			dict(poll_options=['А' * 51, 'Б'], poll_duration='24'),
		]
		for kwargs in bad:
			with self.assertRaises(ValidationError, msg=kwargs):
				publish_post(self.ann.profile, 'вопрос', **kwargs)
		with self.assertRaises(ValidationError):
			publish_post(self.ann.profile, '', poll_options=['А', 'Б'], poll_duration='24')
		self.assertEqual(Poll.objects.count(), 1)
		self.assertAlmostEqual(self.post.poll.ends_at, timezone.now() + timedelta(hours=24), delta=timedelta(minutes=1))

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

	def test_vote_through_repost_and_bad_option(self):
		toggle_repost(self.post, self.bob.profile)
		row = Post.objects.get(repost_of=self.post)
		self.client.force_login(self.cat)
		self.assertEqual(self.client.post(reverse('post-vote', args=[row.pk]), {'option': 'x'}, **HX).status_code, 400)
		self.client.post(reverse('post-vote', args=[row.pk]), {'option': self.tea.pk}, **HX)
		self.assertEqual(PollVote.objects.get().option, self.tea)

	def test_compose_with_poll_and_no_images(self):
		self.client.force_login(self.bob)
		response = self.client.post(reverse('compose'), {
			'text': 'Куда поедем?', 'poll_option': ['Море', 'Горы'], 'poll_duration': '72',
		}, **HX)
		self.assertContains(response, 'Море')
		self.assertTrue(Poll.objects.filter(post__text='Куда поедем?').exists())

	def test_export_purge_erase(self):
		vote(self.post, self.bob.profile, self.tea.pk)
		data, _ = collect_user_data(self.bob)
		self.assertEqual(data['poll_votes'][0]['option'], 'Чай')
		data, _ = collect_user_data(self.ann)
		self.assertEqual(data['posts'][0]['poll']['options'], ['Чай', 'Кофе'])
		erase_account(self.bob)
		self.assertFalse(PollVote.objects.exists())
		delete_post(self.post)
		purge_posts(Post.objects.filter(pk=self.post.pk))
		self.assertFalse(Poll.objects.exists())


class PollEndedNotificationTests(TestCase):
	def setUp(self):
		self.ann, self.bob, self.cat = make('ann'), make('bob'), make('cat')
		self.post = publish_post(self.ann.profile, 'Чай или кофе?', poll_options=['Чай', 'Кофе'], poll_duration='24')
		vote(self.post, self.bob.profile, self.post.poll.options.first().pk)

	def end_poll(self):
		Poll.objects.filter(pk=self.post.poll.pk).update(ends_at=timezone.now() - timedelta(minutes=1))

	def ended(self, user):
		return Notification.objects.filter(recipient=user.profile, verb=Notification.Verb.POLL_ENDED).count()

	def test_author_and_voters_notified_once(self):
		self.assertEqual(unread_count(self.ann), 0)
		self.end_poll()
		with patch('notifications.services.push') as push:
			self.assertEqual(unread_count(self.cat), 0)
		push.assert_called_once()
		self.assertEqual((self.ended(self.ann), self.ended(self.bob), self.ended(self.cat)), (1, 1, 0))
		unread_count(self.ann)
		self.assertEqual(self.ended(self.ann), 1)
		self.client.force_login(self.bob)
		self.assertContains(self.client.get(reverse('notifications')), 'Опрос, в котором вы голосовали, завершён')
		self.client.force_login(self.ann)
		self.assertContains(self.client.get(reverse('notifications')), 'Ваш опрос завершён')

	def test_deleted_post_is_closed_silently(self):
		delete_post(self.post)
		self.end_poll()
		unread_count(self.ann)
		self.assertEqual(self.ended(self.bob), 0)
		self.assertIsNotNone(Poll.objects.get(pk=self.post.poll.pk).closed_at)
