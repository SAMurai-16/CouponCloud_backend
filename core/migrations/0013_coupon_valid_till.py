from datetime import datetime, time
from zoneinfo import ZoneInfo

from django.db import migrations, models


VALID_TILL_BY_MEAL = {
    'B': time(hour=10, minute=0),
    'L': time(hour=14, minute=0),
    'S': time(hour=18, minute=30),
    'D': time(hour=21, minute=0),
}


def backfill_coupon_valid_till(apps, schema_editor):
    Coupon = apps.get_model('core', 'Coupon')
    ist = ZoneInfo('Asia/Kolkata')

    for coupon in Coupon.objects.filter(valid_till__isnull=True).iterator():
        meal_time = VALID_TILL_BY_MEAL.get(coupon.coupon_meal)
        if meal_time is None:
            continue
        coupon.valid_till = datetime.combine(coupon.coupon_date, meal_time, tzinfo=ist)
        coupon.save(update_fields=['valid_till'])


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0012_feedback_hostel_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='coupon',
            name='valid_till',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(
            code=backfill_coupon_valid_till,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name='coupon',
            name='valid_till',
            field=models.DateTimeField(blank=True),
        ),
    ]
