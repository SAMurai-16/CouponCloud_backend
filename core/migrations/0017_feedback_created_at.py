from django.db import migrations, models
from django.utils import timezone


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0016_alter_coupon_qr_image'),
    ]

    operations = [
        migrations.AddField(
            model_name='feedback',
            name='created_at',
            field=models.DateTimeField(db_index=True, default=timezone.now),
        ),
    ]
