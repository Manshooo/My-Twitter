from django import forms
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.core.exceptions import ValidationError
from django.db import transaction
from allauth.account import forms as allauth_forms
from allauth.core import context as allauth_context

from azzb.ratelimit import client_ip
from post.media import ACCEPT, parse_crop, process_cropped_image

from . import captcha
from .models import AVATAR_SIZE, BANNER_SIZE, DEFAULT_AVATAR, USERNAME_MAX_LENGTH, CustomUser

class LoginForm(allauth_forms.LoginForm):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.fields['login'].label = 'Логин или почта'
		self.fields['login'].widget.attrs.pop('placeholder', None)
		self.fields['login'].widget.attrs['autocomplete'] = 'username'
		self.fields['password'].widget.attrs.pop('placeholder', None)
		# allauth кладёт в подсказку HTML-ссылку «Забыли пароль?»; у нас она под формой.
		self.fields['password'].help_text = ''


class SignupForm(allauth_forms.SignupForm):
	# Две отдельные галочки: с 1 сентября 2025 года согласие на обработку ПДн по 152-ФЗ
	# оформляется отдельно от других документов (правил, оферты).
	accept_rules = forms.BooleanField(required=True, error_messages={'required': 'Без согласия с правилами зарегистрироваться нельзя.'})
	pd_consent = forms.BooleanField(required=True, error_messages={'required': 'Без согласия на обработку данных мы не можем создать аккаунт.'})

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		username = self.fields['username']
		username.label = 'Логин'
		username.help_text = f'Будет в адресе профиля. До {USERNAME_MAX_LENGTH} символов: латинские буквы, цифры и _ . -'
		username.widget.attrs.update({'maxlength': USERNAME_MAX_LENGTH})
		self.fields['email'].label = 'Почта'
		self.fields['email'].help_text = 'Пришлём письмо для подтверждения. Никому не показываем.'
		self.fields['password1'].label = 'Пароль'
		self.fields['password2'].label = 'Пароль ещё раз'
		for field in self.fields.values():
			field.widget.attrs.pop('placeholder', None)
		# Галочки — в конце формы, после пароля.
		for name in ('accept_rules', 'pd_consent'):
			self.fields[name] = self.fields.pop(name)
		self.fields['accept_rules'].label = format_html(
			'Принимаю <a href="{}" target="_blank">правила сообщества</a>', reverse('rules'),
		)
		self.fields['pd_consent'].label = format_html(
			'Даю <a href="{}" target="_blank">согласие на обработку персональных данных</a> '
			'на условиях <a href="{}" target="_blank">политики конфиденциальности</a>',
			reverse('pd-consent'), reverse('privacy'),
		)
		# Ключ для виджета капчи в шаблоне; пусто — капча выключена.
		self.captcha_key = settings.SMARTCAPTCHA_CLIENT_KEY if captcha.is_enabled() else ''

	def clean(self):
		cleaned = super().clean()
		if self.captcha_key:
			request = allauth_context.request
			token = self.data.get(captcha.TOKEN_FIELD, '')
			if not captcha.check(token, client_ip(request) if request else ''):
				raise ValidationError('Подтвердите, что вы не робот.')
		return cleaned

	def custom_signup(self, request, user):
		# Хук allauth: пользователь уже сохранён. Фиксируем, когда приняты правила и дано согласие.
		accepted = timezone.now()
		user.terms_accepted_at = accepted
		user.pd_consent_at = accepted
		user.save(update_fields=['terms_accepted_at', 'pd_consent_at'])


class UpdateUserForm(forms.ModelForm):
	class Meta:
		model = CustomUser
		# Почта меняется только через allauth (/auth/email/) — с подтверждением нового адреса.
		fields = ['first_name', 'last_name', 'theme']
		widgets = {'theme': forms.RadioSelect}

	username = forms.CharField(
		label=("Отображаемое имя"),
		max_length=100,
		required=True,
		widget=forms.TextInput,
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
