from datetime import date

from django.core.management.base import BaseCommand, CommandError

from core.models import Coupon


class Command(BaseCommand):
	help = 'Create daily coupons for every student for all meals.'

	def add_arguments(self, parser):
		parser.add_argument(
			'--date',
			dest='coupon_date',
			help='Target date in YYYY-MM-DD format. Defaults to today.',
		)

	def handle(self, *args, **options):
		coupon_date = options.get('coupon_date')

		if coupon_date:
			try:
				coupon_date = date.fromisoformat(coupon_date)
			except ValueError as exc:
				raise CommandError('Date must be in YYYY-MM-DD format.') from exc

		created_count = Coupon.create_daily_coupons(coupon_date=coupon_date)
		target_date = coupon_date.isoformat() if coupon_date else 'today'
		self.stdout.write(
			self.style.SUCCESS(
				f'Created {created_count} coupons for {target_date}.'
			)
		)
