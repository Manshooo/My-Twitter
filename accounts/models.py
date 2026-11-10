from datetime import UTC, datetime
from typing import cast

from django.contrib.postgres.indexes import GinIndex, OpClass
from django.contrib.auth.models import AbstractUser
from django.core import validators
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Exists, F, OuterRef, Q
from django.db.models.functions import Upper
from django.utils import timezone
from django.utils.deconstruct import deconstructible
from django.utils.translation import gettext_lazy as _


def user_profile_avatar_path(instance, filename):
	# файл загрузится в MEDIA_ROOT/users/user_<id>/<filename>
	return f"users/user_{instance.user.id}/{filename}"


def user_profile_banner_path(instance, filename):
	return f"users/user_{instance.user.id}/banner-{filename}"


AVATAR_SIZE = (400, 400)
BANNER_SIZE = (1500, 500)
DEFAULT_AVATAR = 'default/default_user_avatar.jpg'

# Профиль создаётся сигналом в accounts/signals.py.

USERNAME_MAX_LENGTH = 30
# «Навсегда» для banned_until: дата, до которой бан точно не кончится.
BAN_FOREVER = datetime(9999, 1, 1, tzinfo=UTC)

@deconstructible
class UsernameValidator(validators.RegexValidator):
	# Логин попадает в адрес профиля (/users/<логин>/), поэтому только безопасные для URL символы.
	regex = r"^[a-zA-Z0-9_.-]+\Z"
	message = _(
		"Введите верное имя пользователя. Доступны латинские буквы, цифры и символы _ . -"
	)
	flags = 0
class Theme(models.TextChoices):
	# Пустое значение — как в системе (prefers-color-scheme).
	SYSTEM = '', 'Как в системе'
	LIGHT = 'light', 'Светлая'
	DARK = 'dark', 'Тёмная'


class CustomUser(AbstractUser):
	username_validator = UsernameValidator()
	username = models.CharField(
		_("username"),
		# Колонку не сужаем: у старых аккаунтов логин может быть длиннее. Лимит 30 — валидатором.
		max_length=150,
		unique=True,
		help_text=_(
			"До 30 символов: латинские буквы, цифры и _ . -"
		),
		validators=[username_validator, validators.MaxLengthValidator(USERNAME_MAX_LENGTH)],
		error_messages={
			"unique": _("A user with that username already exists."),
		},
	)
	last_visit = models.DateTimeField("Последний раз в сети", default=None, null=True)
	# Тема хранится в аккаунте, а не только в cookie: выбор переезжает на все устройства.
	# Поле у пользователя, а не у Profile, — request.user уже загружен, лишнего запроса нет.
	theme = models.CharField("Тема оформления", max_length=5, choices=Theme.choices, blank=True, default=Theme.SYSTEM)
	# Текущий бан (E4); история — moderation.Ban. Срок в прошлом — бан закончился сам.
	# Бессрочный бан — BAN_FOREVER. Ставится только через moderation.services.ban_user.
	banned_until = models.DateTimeField("Забанен до", null=True, blank=True)
	ban_reason = models.CharField("Причина бана", max_length=500, blank=True, default="")
	# Когда человек принял правила и дал согласие на обработку ПДн (E6, 152-ФЗ). Пусто — аккаунт
	# заведён до появления галочек на регистрации.
	terms_accepted_at = models.DateTimeField("Принял правила", null=True, blank=True)
	pd_consent_at = models.DateTimeField("Согласие на обработку ПДн", null=True, blank=True)
	# Человек удалил аккаунт: тот сразу отключён, а данные стираются через полгода
	# (azzb/retention.py) или сразу, если он об этом попросил (erased_at).
	deleted_at = models.DateTimeField("Удалил аккаунт", null=True, blank=True)
	erased_at = models.DateTimeField("Данные стёрты", null=True, blank=True)

	# Обратная связь от Profile.user: Django создаёт её сам, аннотация — только для редактора.
	profile: 'Profile'

	class Meta(AbstractUser.Meta):
		indexes = [
			# Поиск людей (D3): подстрока (icontains → UPPER(...) LIKE) и похожие написания (%).
			GinIndex(OpClass(Upper('username'), name='gin_trgm_ops'), name='user_username_upper_trgm'),
			GinIndex(fields=['username'], opclasses=['gin_trgm_ops'], name='user_username_trgm'),
		]

	@property
	def is_banned(self):
		return self.banned_until is not None and self.banned_until > timezone.now()

	@property
	def ban_is_permanent(self):
		return self.banned_until is not None and self.banned_until >= BAN_FOREVER


class FollowThrough(models.Model):
	follower_id: int
	followee_id: int

	follower = models.ForeignKey('Profile', on_delete=models.CASCADE, related_name='following_set')
	followee = models.ForeignKey('Profile', on_delete=models.CASCADE, related_name='followee_set')
	created_at = models.DateTimeField("Когда подписался", auto_now_add=True)

	class Meta:
		verbose_name = 'Подписка'
		verbose_name_plural = 'Подписки'
		constraints = [
			models.UniqueConstraint(fields=['follower', 'followee'], name='follow_once'),
			models.CheckConstraint(condition=~Q(follower=F('followee')), name='not_follow_self')
		]

	def __str__(self):
		return f'{self.follower} → {self.followee}'

	def clean(self):
		if self.follower_id == self.followee_id:
			raise ValidationError('Can not follow self.')


class ProfileQuerySet(models.QuerySet['Profile']):
	def public(self):
		"""Единственное место, которое решает, кого из людей показывать другим (как
		Post.objects.visible_to для постов): аккаунт не удалён и не отключён, регистрация завершена.

		Регистрация через сайт заводит профиль сразу, а войти можно только после подтверждения почты
		(ACCOUNT_EMAIL_VERIFICATION = 'mandatory'). Брошенные регистрации — боты, опечатки в адресе —
		прячем: у них есть адрес, но ни один не подтверждён. Аккаунты без адресов вовсе (createsuperuser,
		админка) — заведены вручную и видны. При смене почты старый подтверждённый адрес живёт,
		пока не подтвердят новый, так что профиль не пропадает.
		Забаненных не прячем: профиль открывается, а посты скрывает Post.objects.visible_to.
		"""
		from allauth.account.models import EmailAddress  # приложения allauth грузятся после accounts

		addresses = EmailAddress.objects.filter(user_id=OuterRef('user_id'))
		return self.filter(
			Exists(addresses.filter(verified=True)) | ~Exists(addresses),
			user__is_active=True, user__deleted_at__isnull=True,
		)


class Profile(models.Model):

	id = models.BigAutoField(primary_key=True)
	user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name="profile")
	username = models.CharField("Отображаемое имя пользователя", max_length=150, default=None, blank=True)
	avatar = models.ImageField(default=DEFAULT_AVATAR, upload_to=user_profile_avatar_path)
	# Обложка 3:1 над профилем. Как и аватар, загружается уже обрезанной и в WebP.
	banner = models.ImageField("Баннер", upload_to=user_profile_banner_path, blank=True, default='')
	bio = models.CharField("О себе", max_length=250, blank=True, default="")
	# Галочка «подтверждённый аккаунт» ставится вручную в админке; значок staff — отдельно, по user.is_staff.
	is_verified = models.BooleanField("Подтверждённый аккаунт", default=False)
	likes_public = models.BooleanField("Показывать лайки всем", default=False)
	# Закрытый аккаунт (E5): посты видят только одобренные подписчики, подписка — через заявку.
	is_private = models.BooleanField("Закрытый аккаунт", default=False)
	# Закреплённый пост (B8): первым на вкладке «Посты». Только свой пост, меняется через post.services.toggle_pin.
	pinned_post = models.ForeignKey(
		'post.Post', verbose_name="Закреплённый пост", null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
	)
	follows = models.ManyToManyField(
		"self",
		verbose_name="Подписчики",
		related_name="followed_by",
		symmetrical=False,
		blank=True,
		through=FollowThrough,
		through_fields=('follower', 'followee'),
	)

	# cast — только для подсказок типов: as_manager() теряет методы ProfileQuerySet (public и т. п.).
	objects = cast(ProfileQuerySet, ProfileQuerySet.as_manager())
	user_id: int

	class Meta:
		verbose_name = 'Профиль'
		verbose_name_plural = 'Профили'
		indexes = [
			GinIndex(OpClass(Upper('username'), name='gin_trgm_ops'), name='profile_name_upper_trgm'),
			GinIndex(fields=['username'], opclasses=['gin_trgm_ops'], name='profile_name_trgm'),
		]

	def __str__(self):
		return self.username

	def save(self, *args, **kwargs):
		if not self.username:
			self.username = self.user.username
		super().save(*args, **kwargs)

	@property
	def has_custom_avatar(self):
		return bool(self.avatar) and self.avatar.name != self._meta.get_field('avatar').default

	@property
	def avatar_tone(self):
		# Цвет буквенного аватара из 5 пар токенов --avN-bg/--avN-ink, стабильный для пользователя.
		return (self.user_id or 0) % 5 + 1

	@property
	def initial(self):
		name = (self.username or self.user.username or '?').strip()
		return name[:1].upper() or '?'


class FollowRequest(models.Model):
	"""Заявка на подписку на закрытый аккаунт (E5). Одобрение превращает её в FollowThrough.
	Создаётся и разбирается только через accounts.relations."""
	requester = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='follow_requests_sent')
	target = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='follow_requests')
	created_at = models.DateTimeField('Когда', auto_now_add=True)

	class Meta:
		verbose_name = 'Заявка на подписку'
		verbose_name_plural = 'Заявки на подписку'
		constraints = [
			models.UniqueConstraint(fields=['requester', 'target'], name='follow_request_once'),
			models.CheckConstraint(condition=~Q(requester=F('target')), name='not_request_self'),
		]

	def __str__(self):
		return f'{self.requester} → {self.target} (заявка)'


class Block(models.Model):
	"""Блокировка (E3): ни один из двоих не видит посты другого, не может подписаться,
	ответить или лайкнуть. При блокировке подписки в обе стороны снимаются.
	Фильтр постов — в Post.objects.visible_to (единая точка видимости)."""
	blocker = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='blocking_set')
	blocked = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='blocked_by_set')
	created_at = models.DateTimeField('Когда', auto_now_add=True)

	class Meta:
		verbose_name = 'Блокировка'
		verbose_name_plural = 'Блокировки'
		constraints = [
			models.UniqueConstraint(fields=['blocker', 'blocked'], name='block_once'),
			models.CheckConstraint(condition=~Q(blocker=F('blocked')), name='not_block_self'),
		]

	def __str__(self):
		return f'{self.blocker} ⊘ {self.blocked}'


class Mute(models.Model):
	"""Заглушить (E3): посты человека пропадают из моих лент, но профиль и ветки открываются,
	и он ничего об этом не знает. Подписка остаётся."""
	muter = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='muting_set')
	muted = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='muted_by_set')
	created_at = models.DateTimeField('Когда', auto_now_add=True)

	class Meta:
		verbose_name = 'Заглушённый'
		verbose_name_plural = 'Заглушённые'
		constraints = [
			models.UniqueConstraint(fields=['muter', 'muted'], name='mute_once'),
			models.CheckConstraint(condition=~Q(muter=F('muted')), name='not_mute_self'),
		]

	def __str__(self):
		return f'{self.muter} 🔇 {self.muted}'
