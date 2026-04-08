from datetime import date
from io import BytesIO

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.urls import reverse
from django.test import override_settings
from django.test import TestCase
from rest_framework.test import APIClient
from PIL import Image

from .models import (
	Complaint,
	Coupon,
	CouponMeal,
	CouponTransferRequest,
	CouponTransferStatus,
	Feedback,
	Mess,
	MessMenu,
	MessMenuItem,
	Student,
	UserRole,
	Weekday,
)


@override_settings(MEDIA_ROOT='/tmp/coupon-cloud-test-media')
class CouponModelTests(TestCase):
	def setUp(self):
		self.mess_h1 = Mess.objects.create(
			name='Hostel 1 Mess',
			hostel_id='H1',
		)
		self.mess_h2 = Mess.objects.create(
			name='Hostel 2 Mess',
			hostel_id='H2',
		)

		self.student = Student.objects.create(
			name='Test Student',
			email='student@example.com',
			role=UserRole.STUDENT,
			student_id='STU001',
			mess=self.mess_h1,
		)
		self.other_student = Student.objects.create(
			name='Second Student',
			email='student2@example.com',
			role=UserRole.STUDENT,
			student_id='STU002',
			mess=self.mess_h2,
		)

	def test_create_coupon(self):
		coupon = Coupon.objects.create(
			student=self.student,
			hostel_id='H1',
			coupon_id='CPN001',
			coupon_meal=CouponMeal.LUNCH,
			coupon_date=date(2026, 4, 8),
		)

		self.assertEqual(coupon.student.student_id, 'STU001')
		self.assertEqual(coupon.coupon_meal, CouponMeal.LUNCH)
		self.assertEqual(coupon.qr_payload, str(coupon.qr_token))
		self.assertFalse(bool(coupon.qr_image))

	def test_qr_is_created_only_on_first_access(self):
		coupon = Coupon.objects.create(
			student=self.student,
			hostel_id='H1',
			coupon_id='CPN003',
			coupon_meal=CouponMeal.SNACKS,
			coupon_date=date(2026, 4, 8),
		)

		self.assertFalse(bool(coupon.qr_image))

		coupon.ensure_qr_image()
		coupon.refresh_from_db()

		self.assertTrue(coupon.qr_image.name.startswith('coupon_qr/'))
		self.assertTrue(coupon.qr_image.name.endswith('.png'))

	def test_coupon_id_must_be_unique(self):
		Coupon.objects.create(
			student=self.student,
			hostel_id='H1',
			coupon_id='CPN001',
			coupon_meal=CouponMeal.BREAKFAST,
			coupon_date=date(2026, 4, 8),
		)

		with self.assertRaises(IntegrityError):
			Coupon.objects.create(
				student=self.student,
				hostel_id='H1',
				coupon_id='CPN001',
				coupon_meal=CouponMeal.DINNER,
				coupon_date=date(2026, 4, 9),
			)

	def test_qr_payload_comes_from_the_coupon_token(self):
		coupon = Coupon.objects.create(
			student=self.student,
			hostel_id='H2',
			coupon_id='CPN002',
			coupon_meal=CouponMeal.DINNER,
			coupon_date=date(2026, 4, 9),
		)

		self.assertEqual(coupon.build_qr_payload(), str(coupon.qr_token))

	def test_qr_verify_uses_the_current_token(self):
		coupon = Coupon.objects.create(
			student=self.student,
			hostel_id='H1',
			coupon_id='CPN010',
			coupon_meal=CouponMeal.BREAKFAST,
			coupon_date=date(2026, 4, 8),
		)

		response = self.client.post(
			reverse('coupon-verify'),
			{'qr_payload': coupon.qr_payload},
			format='json',
		)

		self.assertEqual(response.status_code, 200)
		self.assertTrue(response.data['valid'])
		self.assertEqual(response.data['coupon']['coupon_id'], coupon.coupon_id)

	def test_create_daily_coupons_creates_all_meals_for_each_student(self):
		created_count = Coupon.create_daily_coupons(coupon_date=date(2026, 4, 10))

		self.assertEqual(created_count, 8)
		self.assertEqual(Coupon.objects.filter(coupon_date=date(2026, 4, 10)).count(), 8)
		self.assertFalse(Coupon.objects.filter(coupon_date=date(2026, 4, 10)).exclude(qr_image='').exists())

	def test_create_daily_coupons_is_idempotent(self):
		Coupon.create_daily_coupons(coupon_date=date(2026, 4, 10))
		created_count = Coupon.create_daily_coupons(coupon_date=date(2026, 4, 10))

		self.assertEqual(created_count, 0)
		self.assertEqual(Coupon.objects.filter(coupon_date=date(2026, 4, 10)).count(), 8)

	def test_management_command_creates_daily_coupons(self):
		call_command('create_daily_coupons', '--date', '2026-04-11')

		self.assertEqual(Coupon.objects.filter(coupon_date=date(2026, 4, 11)).count(), 8)

	def test_accepting_transfer_moves_coupon_and_rotates_qr(self):
		coupon = Coupon.objects.create(
			student=self.student,
			hostel_id='H1',
			coupon_id='CPN020',
			coupon_meal=CouponMeal.LUNCH,
			coupon_date=date(2026, 4, 8),
		)
		coupon.ensure_qr_image()
		old_payload = coupon.qr_payload

		transfer_request = CouponTransferRequest.objects.create(
			coupon=coupon,
			requested_by=self.student,
			requested_to=self.other_student,
			message='Take this coupon.',
		)

		transfer_request.accept()
		coupon.refresh_from_db()
		transfer_request.refresh_from_db()

		self.assertEqual(transfer_request.status, CouponTransferStatus.ACCEPTED)
		self.assertIsNotNone(transfer_request.responded_at)
		self.assertEqual(coupon.student_id, self.other_student.user_id)
		self.assertNotEqual(coupon.qr_payload, old_payload)
		self.assertEqual(coupon.qr_payload, str(coupon.qr_token))

		verify_response = self.client.post(
			reverse('coupon-verify'),
			{'qr_payload': old_payload},
			format='json',
		)

		self.assertEqual(verify_response.status_code, 404)

	def test_rejecting_transfer_keeps_coupon_with_original_owner(self):
		coupon = Coupon.objects.create(
			student=self.student,
			hostel_id='H1',
			coupon_id='CPN021',
			coupon_meal=CouponMeal.DINNER,
			coupon_date=date(2026, 4, 8),
		)
		transfer_request = CouponTransferRequest.objects.create(
			coupon=coupon,
			requested_by=self.student,
			requested_to=self.other_student,
		)

		transfer_request.reject()
		coupon.refresh_from_db()
		transfer_request.refresh_from_db()

		self.assertEqual(transfer_request.status, CouponTransferStatus.REJECTED)
		self.assertEqual(coupon.student_id, self.student.user_id)
		self.assertEqual(coupon.qr_payload, str(coupon.qr_token))


class MessMenuModelTests(TestCase):
	def setUp(self):
		self.mess = Mess.objects.create(
			name='Hostel 1 Mess',
			hostel_id='H1',
		)

	def test_menu_can_store_multiple_items_for_a_meal(self):
		menu = MessMenu.objects.create(
			mess=self.mess,
			day_of_week=Weekday.MONDAY,
			meal=CouponMeal.BREAKFAST,
		)

		MessMenuItem.objects.create(menu=menu, name='Idli', display_order=1)
		MessMenuItem.objects.create(menu=menu, name='Sambar', display_order=2)
		MessMenuItem.objects.create(menu=menu, name='Chutney', display_order=3)

		self.assertEqual(menu.items.count(), 3)
		self.assertEqual(list(menu.items.values_list('name', flat=True)), ['Idli', 'Sambar', 'Chutney'])

	def test_menu_is_unique_per_mess_day_and_meal(self):
		MessMenu.objects.create(
			mess=self.mess,
			day_of_week=Weekday.MONDAY,
			meal=CouponMeal.LUNCH,
		)

		with self.assertRaises(IntegrityError):
			MessMenu.objects.create(
				mess=self.mess,
				day_of_week=Weekday.MONDAY,
				meal=CouponMeal.LUNCH,
			)


class MessMenuApiTests(TestCase):
	def setUp(self):
		self.client = APIClient()
		self.mess = Mess.objects.create(
			name='Hostel 1 Mess',
			hostel_id='H1',
		)

	def test_create_mess_menu_with_items(self):
		response = self.client.post(
			reverse('mess-menu-list-create'),
			{
				'hostel_id': self.mess.hostel_id,
				'day_of_week': Weekday.MONDAY,
				'meal': CouponMeal.BREAKFAST,
				'items': [
					{'name': 'Idli', 'display_order': 1},
					{'name': 'Sambar', 'display_order': 2},
				],
			},
			format='json',
		)

		self.assertEqual(response.status_code, 201)
		self.assertEqual(response.data['mess']['id'], self.mess.id)
		self.assertEqual(len(response.data['items']), 2)
		self.assertEqual(response.data['items'][0]['name'], 'Idli')

	def test_get_mess_menus(self):
		menu = MessMenu.objects.create(
			mess=self.mess,
			day_of_week=Weekday.TUESDAY,
			meal=CouponMeal.LUNCH,
		)
		MessMenuItem.objects.create(menu=menu, name='Rice', display_order=1)
		MessMenuItem.objects.create(menu=menu, name='Dal', display_order=2)

		response = self.client.get(reverse('mess-menu-list-create'))

		self.assertEqual(response.status_code, 200)
		self.assertEqual(len(response.data), 1)
		self.assertEqual(response.data[0]['meal'], CouponMeal.LUNCH)
		self.assertEqual(len(response.data[0]['items']), 2)

	def test_get_single_mess_menu(self):
		menu = MessMenu.objects.create(
			mess=self.mess,
			day_of_week=Weekday.WEDNESDAY,
			meal=CouponMeal.DINNER,
		)
		MessMenuItem.objects.create(menu=menu, name='Chapati', display_order=1)

		response = self.client.get(reverse('mess-menu-detail', kwargs={'menu_id': menu.id}))

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data['id'], menu.id)
		self.assertEqual(response.data['items'][0]['name'], 'Chapati')


@override_settings(MEDIA_ROOT='/tmp/coupon-cloud-test-media')
class CouponTransferApiTests(TestCase):
	def setUp(self):
		self.client = APIClient()
		self.mess = Mess.objects.create(
			name='Hostel 1 Mess',
			hostel_id='H1',
		)
		self.student = Student.objects.create(
			name='Sender Student',
			email='sender@example.com',
			role=UserRole.STUDENT,
			student_id='STU300',
			mess=self.mess,
		)
		self.recipient = Student.objects.create(
			name='Recipient Student',
			email='recipient@example.com',
			role=UserRole.STUDENT,
			student_id='STU301',
			mess=self.mess,
		)

	def test_create_transfer_request(self):
		coupon = Coupon.objects.create(
			student=self.student,
			hostel_id='H1',
			coupon_id='CPN030',
			coupon_meal=CouponMeal.BREAKFAST,
			coupon_date=date(2026, 4, 12),
		)

		self.client.force_authenticate(user=self.student)
		response = self.client.post(
			reverse('coupon-transfer-request-create'),
			{
				'coupon_id': coupon.coupon_id,
				'requested_to_student_id': self.recipient.student_id,
				'message': 'Please take this one.',
			},
			format='json',
		)

		self.assertEqual(response.status_code, 201)
		self.assertEqual(response.data['status'], CouponTransferStatus.PENDING)
		self.assertEqual(response.data['requested_to']['student_id'], self.recipient.student_id)

	def test_recipient_can_accept_transfer(self):
		coupon = Coupon.objects.create(
			student=self.student,
			hostel_id='H1',
			coupon_id='CPN031',
			coupon_meal=CouponMeal.LUNCH,
			coupon_date=date(2026, 4, 12),
		)
		transfer_request = CouponTransferRequest.objects.create(
			coupon=coupon,
			requested_by=self.student,
			requested_to=self.recipient,
		)

		self.client.force_authenticate(user=self.recipient)
		response = self.client.post(reverse('coupon-transfer-request-accept', kwargs={'transfer_id': transfer_request.id}))

		self.assertEqual(response.status_code, 200)
		transfer_request.refresh_from_db()
		coupon.refresh_from_db()
		self.assertEqual(transfer_request.status, CouponTransferStatus.ACCEPTED)
		self.assertEqual(coupon.student_id, self.recipient.user_id)

	def test_old_qr_payload_fails_after_acceptance(self):
		coupon = Coupon.objects.create(
			student=self.student,
			hostel_id='H1',
			coupon_id='CPN032',
			coupon_meal=CouponMeal.DINNER,
			coupon_date=date(2026, 4, 12),
		)
		old_payload = coupon.qr_payload
		transfer_request = CouponTransferRequest.objects.create(
			coupon=coupon,
			requested_by=self.student,
			requested_to=self.recipient,
		)

		self.client.force_authenticate(user=self.recipient)
		accept_response = self.client.post(reverse('coupon-transfer-request-accept', kwargs={'transfer_id': transfer_request.id}))
		self.assertEqual(accept_response.status_code, 200)

		verify_response = self.client.post(
			reverse('coupon-verify'),
			{'qr_payload': old_payload},
			format='json',
		)

		self.assertEqual(verify_response.status_code, 404)


@override_settings(MEDIA_ROOT='/tmp/coupon-cloud-test-media')
class FeedbackAndComplaintModelTests(TestCase):
	def setUp(self):
		self.mess = Mess.objects.create(
			name='Hostel 1 Mess',
			hostel_id='H1',
		)

		self.student = Student.objects.create(
			name='Feedback Student',
			email='feedback.student@example.com',
			role=UserRole.STUDENT,
			student_id='STU100',
			mess=self.mess,
		)

	def test_feedback_rating_must_be_between_one_and_five(self):
		feedback = Feedback(
			raised_by=self.student,
			coupon_meal=CouponMeal.LUNCH,
			rating=6,
			description='Too high',
		)

		with self.assertRaises(ValidationError):
			feedback.full_clean()

	def test_feedback_with_valid_rating_is_saved(self):
		feedback = Feedback.objects.create(
			raised_by=self.student,
			coupon_meal=CouponMeal.LUNCH,
			rating=4,
			description='Food was good',
		)

		self.assertEqual(feedback.rating, 4)
		self.assertEqual(feedback.description, 'Food was good')
		self.assertEqual(feedback.raised_by.student_id, 'STU100')
		self.assertEqual(feedback.coupon_meal, CouponMeal.LUNCH)

	def test_complaint_can_store_photo_and_description(self):
		photo = SimpleUploadedFile(
			'complaint.jpg',
			b'filecontent',
			content_type='image/jpeg',
		)

		complaint = Complaint.objects.create(
			raised_by=self.student,
			mess=self.mess,
			coupon_meal=CouponMeal.LUNCH,
			complaint_type='Hygiene',
			photo=photo,
			description='Dining area was not clean.',
		)

		self.assertEqual(complaint.complaint_type, 'Hygiene')
		self.assertEqual(complaint.description, 'Dining area was not clean.')
		self.assertEqual(complaint.raised_by.student_id, 'STU100')
		self.assertEqual(complaint.mess.hostel_id, 'H1')
		self.assertEqual(complaint.coupon_meal, CouponMeal.LUNCH)
		self.assertTrue(complaint.photo.name.startswith('complaints/'))


@override_settings(MEDIA_ROOT='/tmp/coupon-cloud-test-media')
class FeedbackAndComplaintApiTests(TestCase):
	def setUp(self):
		self.client = APIClient()
		self.mess = Mess.objects.create(
			name='Hostel 1 Mess',
			hostel_id='H1',
		)

		self.student = Student.objects.create(
			name='API Student',
			email='api.student@example.com',
			role=UserRole.STUDENT,
			student_id='STU200',
			mess=self.mess,
		)

	def test_create_feedback(self):
		response = self.client.post(
			reverse('feedback-list-create'),
			{
				'raised_by_id': self.student.user_id,
				'coupon_meal': CouponMeal.DINNER,
				'rating': 5,
				'description': 'Very good dinner.',
			},
			format='json',
		)

		self.assertEqual(response.status_code, 201)
		self.assertEqual(response.data['coupon_meal'], CouponMeal.DINNER)
		self.assertEqual(response.data['raised_by']['user_id'], self.student.user_id)

	def test_create_complaint(self):
		image_buffer = BytesIO()
		Image.new('RGB', (1, 1), color='white').save(image_buffer, format='PNG')
		photo = SimpleUploadedFile('complaint.png', image_buffer.getvalue(), content_type='image/png')

		response = self.client.post(
			reverse('complaint-list-create'),
			{
				'raised_by_id': self.student.user_id,
				'hostel_id': self.mess.hostel_id,
				'coupon_meal': CouponMeal.BREAKFAST,
				'complaint_type': 'Food Quality',
				'photo': photo,
				'description': 'Breakfast quality was poor.',
			},
		)

		self.assertEqual(response.status_code, 201)
		self.assertEqual(response.data['coupon_meal'], CouponMeal.BREAKFAST)
		self.assertEqual(response.data['mess']['id'], self.mess.id)

	def test_list_feedbacks_and_complaints(self):
		Feedback.objects.create(
			raised_by=self.student,
			coupon_meal=CouponMeal.LUNCH,
			rating=4,
			description='Good lunch.',
		)
		Complaint.objects.create(
			raised_by=self.student,
			mess=self.mess,
			coupon_meal=CouponMeal.SNACKS,
			complaint_type='Hygiene',
			photo=SimpleUploadedFile('complaint2.jpg', b'filecontent', content_type='image/jpeg'),
			description='Snacks counter was not clean.',
		)

		feedback_response = self.client.get(reverse('feedback-list-create'))
		complaint_response = self.client.get(reverse('complaint-list-create'))

		self.assertEqual(feedback_response.status_code, 200)
		self.assertEqual(len(feedback_response.data), 1)
		self.assertEqual(complaint_response.status_code, 200)
		self.assertEqual(len(complaint_response.data), 1)
