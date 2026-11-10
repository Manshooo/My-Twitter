# Время подписки — для уведомлений «подписался на вас» и рекомендаций.
# Для старых подписок настоящее время неизвестно: ставим более позднюю из дат
# регистрации двух пользователей (раньше этого момента подписки быть не могло).

import django.utils.timezone
from django.db import migrations, models


def backfill_follow_dates(apps, schema_editor):
	FollowThrough = apps.get_model('customUser', 'FollowThrough')
	for follow in FollowThrough.objects.select_related('follower__user', 'followee__user').iterator():
		follow.created_at = max(follow.follower.user.date_joined, follow.followee.user.date_joined)
		follow.save(update_fields=['created_at'])


class Migration(migrations.Migration):

	dependencies = [
		('customUser', '0003_follows_through_fields'),
	]

	operations = [
		migrations.AddField(
			model_name='followthrough',
			name='created_at',
			field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now, verbose_name='Когда подписался'),
			preserve_default=False,
		),
		migrations.RunPython(backfill_follow_dates, migrations.RunPython.noop),
	]
