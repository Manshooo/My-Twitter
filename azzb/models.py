from django.db import models


class RateCounter(models.Model):
	"""Счётчик запросов в окне времени для лимитов частоты (azzb/ratelimit.py).

	Увеличивается одним атомарным INSERT … ON CONFLICT, поэтому верно считает при любом
	числе воркеров. Просроченные строки периодически удаляются там же.
	"""
	key = models.CharField(max_length=200)
	window = models.BigIntegerField('Номер окна')
	hits = models.PositiveIntegerField(default=0)
	expires_at = models.DateTimeField(db_index=True)

	class Meta:
		constraints = [models.UniqueConstraint(fields=['key', 'window'], name='rate_counter_key_window')]

	def __str__(self):
		return f'{self.key} #{self.window}: {self.hits}'
