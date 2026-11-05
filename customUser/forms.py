from django import forms
from django.contrib.auth.forms import PasswordChangeForm, UserCreationForm
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from post.media import ACCEPT, parse_crop, process_cropped_image

from .models import AVATAR_SIZE, BANNER_SIZE, DEFAULT_AVATAR, USERNAME_MAX_LENGTH, CustomUser

class CustomUserCreationForm(UserCreationForm):
	email = forms.EmailField(
		label=_("Email"),
		widget=forms.EmailInput(),
		help_text=validate_email.message
	)

	class Meta:
		model = CustomUser
		fields = ('username', 'email', 'password1', 'password2')
		labels = {'username': 'Логин'}

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.fields['username'].widget.attrs.update({'maxlength': USERNAME_MAX_LENGTH, 'autocomplete': 'username'})
class UpdateUserForm(forms.ModelForm):
	class Meta:
		model = CustomUser
		fields = ['email', 'first_name', 'last_name']

	username = forms.CharField(
		label=("Отображаемое имя"),
		max_length=100,
		required=True,
		widget=forms.TextInput,
	)
	email =  forms.EmailField(
		label=_("Email"),
		required=True,
		widget=forms.EmailInput(),
	)
	first_name = forms.CharField(
		label=("Имя"),
		max_length=50,
		required=False,
		widget=forms.TextInput
	)
	last_name = forms.CharField(
		label=("Фамилия"),
		max_length=50,
		required=False,
		widget=forms.TextInput
	)
	bio = forms.CharField(
		label=("О себе"),
		max_length=250,
		required=False,
		widget=forms.Textarea(attrs={'rows': 4, 'maxlength': 250}),
	)
	likes_public = forms.BooleanField(
		label="Показывать мои лайки всем",
		help_text="Иначе вкладку «Лайки» в профиле видите только вы.",
		required=False,
	)

	# Картинки обрабатываются в post/media.py: обрезка по области из браузера (или по центру),
	# уменьшение, WebP без EXIF. Поэтому здесь FileField, а не ImageField.
	avatar = forms.FileField(label="Аватар", required=False, widget=forms.ClearableFileInput(attrs={'accept': ACCEPT}))
	avatar_crop = forms.CharField(required=False, widget=forms.HiddenInput)
	avatar_clear = forms.BooleanField(label="Убрать аватар", required=False)
	banner = forms.FileField(label="Баннер", required=False, widget=forms.ClearableFileInput(attrs={'accept': ACCEPT}))
	banner_crop = forms.CharField(required=False, widget=forms.HiddenInput)
	banner_clear = forms.BooleanField(label="Убрать баннер", required=False)

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		if 'instance' in kwargs:
			instance = kwargs['instance']
			if hasattr(instance, 'profile'):
				self.fields['bio'].initial = instance.profile.bio
				self.fields['username'].initial = instance.profile.username
				self.fields['likes_public'].initial = instance.profile.likes_public
		# Обычный <input type=file> без «Очистить» от ClearableFileInput: для этого свои флажки.
		for name in ('avatar', 'banner'):
			self.fields[name].widget = forms.FileInput(attrs={'accept': ACCEPT, 'class': 'sr', 'data-crop-input': name})

	def _process(self, name, size):
		upload = self.cleaned_data.get(name)
		if not upload:
			return None
		try:
			return process_cropped_image(upload, size, parse_crop(self.cleaned_data.get(f'{name}_crop')))
		except ValidationError as error:
			self.add_error(name, error)
			return None

	def clean(self):
		cleaned = super().clean()
		self.processed = {
			'avatar': self._process('avatar', AVATAR_SIZE),
			'banner': self._process('banner', BANNER_SIZE),
		}
		return cleaned

	def _replace_image(self, profile, name, empty):
		"""Новая картинка или очистка поля. Старый файл удаляем после коммита."""
		field = getattr(profile, name)
		old_name = field.name if field and field.name != empty else None
		processed = self.processed.get(name)
		if processed:
			field.save(processed.content.name, processed.content, save=False)
		elif self.cleaned_data.get(f'{name}_clear'):
			setattr(profile, name, empty)
		else:
			return
		if old_name:
			storage = field.storage
			transaction.on_commit(lambda: storage.delete(old_name))

	def save(self, commit=True):
		user = super().save(commit=False)
		if commit:
			user.save()
			if hasattr(user, 'profile'):
				profile = user.profile
				profile.bio = self.cleaned_data['bio']
				profile.username = self.cleaned_data['username']
				profile.likes_public = self.cleaned_data['likes_public']
				self._replace_image(profile, 'avatar', DEFAULT_AVATAR)
				self._replace_image(profile, 'banner', '')
				profile.save()
		return user
