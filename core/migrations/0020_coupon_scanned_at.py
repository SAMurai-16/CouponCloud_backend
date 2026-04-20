from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0019_alter_feedback_description'),
    ]

    operations = [
        migrations.AddField(
            model_name='coupon',
            name='scanned_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
