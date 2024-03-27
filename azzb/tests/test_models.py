from django.test import TestCase

from customUser.models import CustomUser

class CustomUserCreationTest(TestCase):
	@classmethod
	def setUpTestData(cls):
		CustomUser.objects.create(username='test', email='test@test.com', password='123JQuery321')
	def setUp(self):
		pass

class ProfileCreationTest(CustomUserCreationTest):

	def test_profile_created(self):
		user = CustomUser.objects.get(id=1)
		profile = user.profile
		self.assertEqual(profile.user, user)
	def test_profile_username(self):
		user = CustomUser.objects.get(id=1)
		profile = user.profile
		self.assertEqual(profile.username, 'test' or user.username)