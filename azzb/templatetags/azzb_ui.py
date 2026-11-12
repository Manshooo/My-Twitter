from datetime import timedelta

from django import template
from django.utils import timezone
from django.utils.dateformat import format as date_format

register = template.Library()


@register.filter
def ago(value, mode=''):
	"""Короткое относительное время, как в макете: «сейчас», «5 мин», «2 ч», «вчера», «28 мая».

	С аргументом "long" минуты и часы получают «назад»: «5 мин назад».
	"""
	if not value:
		return ''
	now = timezone.now()
	value_local = timezone.localtime(value)
	now_local = timezone.localtime(now)
	delta = now - value
	suffix = ' назад' if mode == 'long' else ''
	if delta < timedelta(minutes=1):
		return 'только что' if mode == 'long' else 'сейчас'
	if delta < timedelta(hours=1):
		return f'{int(delta.total_seconds() // 60)} мин{suffix}'
	if delta < timedelta(hours=24) and value_local.date() == now_local.date():
		return f'{int(delta.total_seconds() // 3600)} ч{suffix}'
	if value_local.date() == now_local.date() - timedelta(days=1):
		return 'вчера'
	if value_local.year == now_local.year:
		return date_format(value_local, 'j E')
	return date_format(value_local, 'j E Y')


@register.filter
def msg_time(value):
	"""Время сообщения: «14:05», «вчера, 14:05», «12 ноября, 14:05», в прошлые годы — с годом."""
	if not value:
		return ''
	local = timezone.localtime(value)
	today = timezone.localdate()
	if local.date() == today:
		return date_format(local, 'H:i')
	if local.date() == today - timedelta(days=1):
		return 'вчера, ' + date_format(local, 'H:i')
	return date_format(local, 'j E, H:i' if local.year == today.year else 'j E Y, H:i')


@register.filter
def linkify(text):
	from post.text import linkify as render
	return render(text)


@register.filter
def plural_ru(number, forms):
	"""{{ n|plural_ru:"подписка,подписки,подписок" }} → форма слова для числа n."""
	one, few, many = forms.split(',')
	n = abs(int(number or 0))
	if n % 10 == 1 and n % 100 != 11:
		return one
	if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
		return few
	return many


@register.filter
def count(number):
	"""Счётчик под постом: 0 → «», 1234 → «1,2 тыс.», 12345 → «12 тыс.», 1,2 млн. Пара в JS — formatCount (util.js)."""
	n = int(number or 0)
	for size, unit in ((1_000_000, 'млн'), (1_000, 'тыс.')):
		if n >= size:
			# Отбрасываем, а не округляем: 999 999 — «999 тыс.», а не «1000 тыс.».
			tenths = n * 10 // size
			text = f'{tenths // 10},{tenths % 10}' if tenths < 100 and tenths % 10 else str(tenths // 10)
			return f'{text} {unit}'
	return str(n) if n > 0 else ''


@register.filter
def digits(number):
	"""Полное число с узким неразрывным пробелом между разрядами: 15800 → «15 800»."""
	return f'{int(number or 0):,}'.replace(',', '\u202f')


@register.inclusion_tag('azzb/includes/avatar.html')
def avatar(profile, size=''):
	return {'profile': profile, 'size': size}


@register.inclusion_tag('azzb/includes/badges.html')
def badges(profile):
	return {'profile': profile}
