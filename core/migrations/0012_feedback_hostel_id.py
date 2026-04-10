from django.db import migrations, models


def backfill_feedback_hostel_id(apps, schema_editor):
    Feedback = apps.get_model('core', 'Feedback')
    Student = apps.get_model('core', 'Student')
    Staff = apps.get_model('core', 'Staff')

    hostel_by_user_id = {}

    for student in Student.objects.select_related('mess').all().iterator():
        hostel_by_user_id[student.pk] = student.mess.hostel_id

    for staff in Staff.objects.select_related('mess').all().iterator():
        hostel_by_user_id[staff.pk] = staff.mess.hostel_id

    for feedback in Feedback.objects.filter(hostel_id='').iterator():
        derived_hostel_id = hostel_by_user_id.get(feedback.raised_by_id, '')
        if derived_hostel_id:
            feedback.hostel_id = derived_hostel_id
            feedback.save(update_fields=['hostel_id'])


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0011_coupon_qr_token_and_payload_unique'),
    ]

    operations = [
        migrations.AddField(
            model_name='feedback',
            name='hostel_id',
            field=models.CharField(blank=True, db_index=True, default='', max_length=50),
        ),
        migrations.RunPython(
            code=backfill_feedback_hostel_id,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
