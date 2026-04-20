from datetime import date
from datetime import datetime
from io import BytesIO
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.admin.sites import AdminSite
from django.db import IntegrityError
from django.urls import reverse
from django.test import override_settings
from django.test import TestCase
from rest_framework.test import APIClient
from PIL import Image

from .admin import CouponExchangeRequestAdmin
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
	Staff,
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
		self.staff_h1 = Staff.objects.create(
			name='Hostel 1 Vendor',
			email='vendorh1@example.com',
			role=UserRole.STAFF,
			staff_id='STA001',
			mess=self.mess_h1,
		)
		self.staff_h2 = Staff.objects.create(
			name='Hostel 2 Vendor',
			email='vendorh2@example.com',
			role=UserRole.STAFF,
			staff_id='STA002',
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
		self.assertEqual(
			coupon.valid_till.astimezone(ZoneInfo('Asia/Kolkata')),
			datetime(2026, 4, 8, 14, 0, tzinfo=ZoneInfo('Asia/Kolkata')),
		)
		self.assertFalse(bool(coupon.qr_image))

	def test_valid_till_is_derived_per_meal(self):
		breakfast_coupon = Coupon.objects.create(
			student=self.student,
			hostel_id='H1',
			coupon_id='CPN002A',
			coupon_meal=CouponMeal.BREAKFAST,
			coupon_date=date(2026, 4, 8),
		)
		snack_coupon = Coupon.objects.create(
			student=self.student,
			hostel_id='H1',
			coupon_id='CPN002B',
			coupon_meal=CouponMeal.SNACKS,
			coupon_date=date(2026, 4, 8),
		)

		self.assertEqual(
			breakfast_coupon.valid_till.astimezone(ZoneInfo('Asia/Kolkata')).time(),
			datetime(2026, 4, 8, 10, 0, tzinfo=ZoneInfo('Asia/Kolkata')).time(),
		)
		self.assertEqual(
			snack_coupon.valid_till.astimezone(ZoneInfo('Asia/Kolkata')).time(),
			datetime(2026, 4, 8, 18, 30, tzinfo=ZoneInfo('Asia/Kolkata')).time(),
		)

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
		self.client.force_authenticate(user=self.staff_h1)

		response = self.client.post(
			reverse('coupon-verify'),
			{'qr_payload': coupon.qr_payload},
			format='json',
		)

		self.assertEqual(response.status_code, 200)
		self.assertTrue(response.data['valid'])
		self.assertEqual(response.data['coupon']['coupon_id'], coupon.coupon_id)
		self.assertIsNotNone(response.data['coupon']['valid_till'])
		self.assertIsNotNone(response.data['coupon']['scanned_at'])

	def test_qr_verify_rejects_coupon_if_already_scanned(self):
		coupon = Coupon.objects.create(
			student=self.student,
			hostel_id='H1',
			coupon_id='CPN011',
			coupon_meal=CouponMeal.LUNCH,
			coupon_date=date(2026, 4, 8),
		)
		self.client.force_authenticate(user=self.staff_h1)

		first_response = self.client.post(
			reverse('coupon-verify'),
			{'qr_payload': coupon.qr_payload},
			format='json',
		)
		second_response = self.client.post(
			reverse('coupon-verify'),
			{'qr_payload': coupon.qr_payload},
			format='json',
		)

		coupon.refresh_from_db()

		self.assertEqual(first_response.status_code, 200)
		self.assertEqual(second_response.status_code, 409)
		self.assertEqual(second_response.data['detail'], 'This coupon has already been scanned.')
		self.assertIsNotNone(coupon.scanned_at)

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
		self.client.force_authenticate(user=self.staff_h1)

		verify_response = self.client.post(
			reverse('coupon-verify'),
			{'qr_payload': old_payload},
			format='json',
		)

		self.assertEqual(verify_response.status_code, 404)

	def test_qr_verify_rejects_unauthenticated_request(self):
		coupon = Coupon.objects.create(
			student=self.student,
			hostel_id='H1',
			coupon_id='CPN040',
			coupon_meal=CouponMeal.BREAKFAST,
			coupon_date=date(2026, 4, 8),
		)

		response = self.client.post(
			reverse('coupon-verify'),
			{'qr_payload': coupon.qr_payload},
			format='json',
		)

		self.assertEqual(response.status_code, 403)

	def test_qr_verify_rejects_other_hostel_vendor(self):
		coupon = Coupon.objects.create(
			student=self.student,
			hostel_id='H1',
			coupon_id='CPN041',
			coupon_meal=CouponMeal.LUNCH,
			coupon_date=date(2026, 4, 8),
		)
		self.client.force_authenticate(user=self.staff_h2)

		response = self.client.post(
			reverse('coupon-verify'),
			{'qr_payload': coupon.qr_payload},
			format='json',
		)

		self.assertEqual(response.status_code, 403)
		self.assertEqual(response.data['detail'], 'You can only verify coupons for your hostel.')

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


class AuthApiTests(TestCase):
	def setUp(self):
		self.client = APIClient()
		self.mess = Mess.objects.create(
			name='Hostel 1 Mess',
			hostel_id='H1',
		)
		self.student = Student.objects.create(
			name='Test Student',
			email='loginstudent@example.com',
			role=UserRole.STUDENT,
			student_id='STU100',
			mess=self.mess,
		)
		self.student.set_password('StrongPass123')
		self.student.save(update_fields=['password'])
		self.staff = Staff.objects.create(
			name='Test Staff',
			email='loginstaff@example.com',
			role=UserRole.STAFF,
			staff_id='STA100',
			mess=self.mess,
		)
		self.staff.set_password('StrongPass123')
		self.staff.save(update_fields=['password'])
		Coupon.create_daily_coupons_for_student(self.student, coupon_date=date(2026, 4, 9))

	def test_login_creates_todays_student_coupons(self):
		response = self.client.post(
			reverse('login'),
			{
				'student_id': 'STU100',
				'password': 'StrongPass123',
			},
			format='json',
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data['daily_coupons_created'], 4)
		self.assertEqual(Coupon.objects.filter(student=self.student).count(), 8)

	def test_login_rejects_unknown_student_id(self):
		response = self.client.post(
			reverse('login'),
			{
				'student_id': 'UNKNOWN',
				'password': 'StrongPass123',
			},
			format='json',
		)

		self.assertEqual(response.status_code, 400)
		self.assertEqual(response.data['detail'][0], 'Invalid student ID or password.')

	def test_staff_login_with_staff_id(self):
		response = self.client.post(
			reverse('login'),
			{
				'staff_id': 'STA100',
				'password': 'StrongPass123',
			},
			format='json',
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data['daily_coupons_created'], 0)
		self.assertEqual(response.data['user']['role'], UserRole.STAFF)
		self.assertEqual(response.data['user']['profile']['staff_id'], 'STA100')

	def test_login_after_cross_hostel_exchange_does_not_crash(self):
		other_mess = Mess.objects.create(
			name='Hostel 2 Mess',
			hostel_id='H2',
		)
		other_student = Student.objects.create(
			name='Other Student',
			email='other.login@example.com',
			role=UserRole.STUDENT,
			student_id='STU200',
			mess=other_mess,
		)
		other_student.set_password('StrongPass123')
		other_student.save(update_fields=['password'])

		transfer_date = date(2026, 4, 20)
		requester_coupon = Coupon.objects.create(
			student=self.student,
			hostel_id='H1',
			coupon_id='20260420-H1-STU100-B',
			coupon_meal=CouponMeal.BREAKFAST,
			coupon_date=transfer_date,
		)
		recipient_coupon = Coupon.objects.create(
			student=other_student,
			hostel_id='H2',
			coupon_id='20260420-H2-STU200-B',
			coupon_meal=CouponMeal.BREAKFAST,
			coupon_date=transfer_date,
		)
		transfer = CouponTransferRequest.objects.create(
			coupon=requester_coupon,
			requested_by=self.student,
			requested_to=other_student,
		)
		transfer.accept()

		response = self.client.post(
			reverse('login'),
			{
				'student_id': 'STU100',
				'password': 'StrongPass123',
			},
			format='json',
		)

		self.assertEqual(response.status_code, 200)
		self.assertTrue(
			Coupon.objects.filter(
				student=self.student,
				coupon_meal=CouponMeal.BREAKFAST,
				coupon_date=transfer_date,
			).exists()
		)
		self.assertEqual(
			Coupon.objects.filter(coupon_id='20260420-H1-STU100-B').count(),
			1,
		)

	def test_signed_in_student_can_fetch_their_coupons(self):
		self.client.force_authenticate(user=self.student)

		response = self.client.get(reverse('coupon-list'))

		self.assertEqual(response.status_code, 200)
		self.assertEqual(len(response.data), 4)
		self.assertTrue(all(coupon['student'] == self.student.user_id for coupon in response.data))

	def test_session_login_can_create_exchange_request(self):
		self.assertTrue(self.client.login(email='loginstudent@example.com', password='StrongPass123'))

		recipient_mess = Mess.objects.create(
			name='Hostel 2 Mess',
			hostel_id='H2',
		)
		recipient = Student.objects.create(
			name='Recipient Student',
			email='recipient.session@example.com',
			role=UserRole.STUDENT,
			student_id='STU101',
			mess=recipient_mess,
		)
		coupon = Coupon.objects.create(
			student=self.student,
			hostel_id='H1',
			coupon_id='CPN100',
			coupon_meal=CouponMeal.BREAKFAST,
			coupon_date=date(2026, 4, 12),
		)
		Coupon.objects.create(
			student=recipient,
			hostel_id='H2',
			coupon_id='CPN100R',
			coupon_meal=CouponMeal.BREAKFAST,
			coupon_date=date(2026, 4, 12),
		)

		response = self.client.post(
			reverse('coupon-exchange-request-create'),
			{
				'coupon_id': coupon.coupon_id,
				'requested_to_student_id': recipient.student_id,
				'message': 'Session cookie exchange request.',
			},
			format='json',
		)

		self.assertEqual(response.status_code, 201)
		self.assertEqual(response.data['requested_by']['student_id'], self.student.student_id)

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
class CouponExchangeApiTests(TestCase):
	def setUp(self):
		self.client = APIClient()
		self.mess = Mess.objects.create(
			name='Hostel 1 Mess',
			hostel_id='H1',
		)
		self.other_mess = Mess.objects.create(
			name='Hostel 2 Mess',
			hostel_id='H2',
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
			mess=self.other_mess,
		)

	def test_create_exchange_request(self):
		coupon = Coupon.objects.create(
			student=self.student,
			hostel_id='H1',
			coupon_id='CPN030',
			coupon_meal=CouponMeal.BREAKFAST,
			coupon_date=date(2026, 4, 12),
		)
		Coupon.objects.create(
			student=self.recipient,
			hostel_id='H2',
			coupon_id='CPN030R',
			coupon_meal=CouponMeal.BREAKFAST,
			coupon_date=date(2026, 4, 12),
		)

		self.client.force_authenticate(user=self.student)
		response = self.client.post(
			reverse('coupon-exchange-request-create'),
			{
				'coupon_id': coupon.coupon_id,
				'requested_to_student_id': self.recipient.student_id,
				'message': 'Please exchange this one.',
			},
			format='json',
		)

		self.assertEqual(response.status_code, 201)
		self.assertEqual(response.data['status'], CouponTransferStatus.PENDING)
		self.assertEqual(response.data['requested_to']['student_id'], self.recipient.student_id)
		self.assertNotEqual(response.data['requested_to']['mess_name'], self.student.mess.name)

	def test_recipient_can_accept_exchange(self):
		sender_coupon_id = 'CPN031'
		recipient_coupon_id = 'CPN031R'
		coupon = Coupon.objects.create(
			student=self.student,
			hostel_id='H1',
			coupon_id=sender_coupon_id,
			coupon_meal=CouponMeal.LUNCH,
			coupon_date=date(2026, 4, 12),
		)
		recipient_coupon = Coupon.objects.create(
			student=self.recipient,
			hostel_id='H2',
			coupon_id=recipient_coupon_id,
			coupon_meal=CouponMeal.LUNCH,
			coupon_date=date(2026, 4, 12),
		)
		transfer_request = CouponTransferRequest.objects.create(
			coupon=coupon,
			requested_by=self.student,
			requested_to=self.recipient,
		)

		self.client.force_authenticate(user=self.recipient)
		response = self.client.post(reverse('coupon-exchange-request-accept', kwargs={'exchange_id': transfer_request.id}))

		self.assertEqual(response.status_code, 200)
		transfer_request.refresh_from_db()
		coupon.refresh_from_db()
		recipient_coupon.refresh_from_db()
		self.assertEqual(transfer_request.status, CouponTransferStatus.ACCEPTED)
		self.assertEqual(coupon.student_id, self.recipient.user_id)
		self.assertEqual(coupon.hostel_id, self.student.mess.hostel_id)
		self.assertEqual(coupon.coupon_id, sender_coupon_id)
		self.assertEqual(recipient_coupon.student_id, self.student.user_id)
		self.assertEqual(recipient_coupon.hostel_id, self.recipient.mess.hostel_id)
		self.assertEqual(recipient_coupon.coupon_id, recipient_coupon_id)

	def test_admin_accept_runs_exchange_logic(self):
		sender_coupon_id = 'CPN033'
		recipient_coupon_id = 'CPN033R'
		coupon = Coupon.objects.create(
			student=self.student,
			hostel_id='H1',
			coupon_id=sender_coupon_id,
			coupon_meal=CouponMeal.BREAKFAST,
			coupon_date=date(2026, 4, 12),
		)
		recipient_coupon = Coupon.objects.create(
			student=self.recipient,
			hostel_id='H2',
			coupon_id=recipient_coupon_id,
			coupon_meal=CouponMeal.BREAKFAST,
			coupon_date=date(2026, 4, 12),
		)
		exchange_request = CouponTransferRequest.objects.create(
			coupon=coupon,
			requested_by=self.student,
			requested_to=self.recipient,
		)

		admin = CouponExchangeRequestAdmin(CouponTransferRequest, AdminSite())
		exchange_request.status = CouponTransferStatus.ACCEPTED
		admin.save_model(object(), exchange_request, form=None, change=True)

		exchange_request.refresh_from_db()
		coupon.refresh_from_db()
		recipient_coupon.refresh_from_db()

		self.assertEqual(exchange_request.status, CouponTransferStatus.ACCEPTED)
		self.assertEqual(coupon.student_id, self.recipient.user_id)
		self.assertEqual(coupon.coupon_id, sender_coupon_id)
		self.assertEqual(recipient_coupon.student_id, self.student.user_id)
		self.assertEqual(recipient_coupon.coupon_id, recipient_coupon_id)

	def test_exchange_request_requires_different_hostels(self):
		other_same_hostel_student = Student.objects.create(
			name='Same Hostel Student',
			email='same.hostel@example.com',
			role=UserRole.STUDENT,
			student_id='STU302',
			mess=self.mess,
		)
		coupon = Coupon.objects.create(
			student=self.student,
			hostel_id='H1',
			coupon_id='CPN031A',
			coupon_meal=CouponMeal.LUNCH,
			coupon_date=date(2026, 4, 12),
		)

		self.client.force_authenticate(user=self.student)
		response = self.client.post(
			reverse('coupon-exchange-request-create'),
			{
				'coupon_id': coupon.coupon_id,
				'requested_to_student_id': other_same_hostel_student.student_id,
				'message': 'This should fail.',
			},
			format='json',
		)

		self.assertEqual(response.status_code, 400)
		self.assertIn('different hostels', str(response.data))

	def test_old_qr_payload_fails_after_acceptance(self):
		coupon = Coupon.objects.create(
			student=self.student,
			hostel_id='H1',
			coupon_id='CPN032',
			coupon_meal=CouponMeal.DINNER,
			coupon_date=date(2026, 4, 12),
		)
		Coupon.objects.create(
			student=self.recipient,
			hostel_id='H2',
			coupon_id='CPN032R',
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
		accept_response = self.client.post(reverse('coupon-exchange-request-accept', kwargs={'exchange_id': transfer_request.id}))
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
		self.assertEqual(feedback.hostel_id, 'H1')
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
		self.assertEqual(response.data['hostel_id'], self.mess.hostel_id)

	def test_create_feedback_without_description(self):
		response = self.client.post(
			reverse('feedback-list-create'),
			{
				'raised_by_id': self.student.user_id,
				'coupon_meal': CouponMeal.LUNCH,
				'rating': 4,
			},
			format='json',
		)

		self.assertEqual(response.status_code, 201)
		self.assertEqual(response.data['description'], '')

	def test_cannot_create_duplicate_feedback_for_same_meal_on_same_day(self):
		Feedback.objects.create(
			raised_by=self.student,
			coupon_meal=CouponMeal.DINNER,
			rating=4,
			description='First dinner feedback.',
		)

		response = self.client.post(
			reverse('feedback-list-create'),
			{
				'raised_by_id': self.student.user_id,
				'coupon_meal': CouponMeal.DINNER,
				'rating': 5,
				'description': 'Second dinner feedback.',
			},
			format='json',
		)

		self.assertEqual(response.status_code, 400)
		self.assertEqual(
			response.data['detail'][0],
			'This user has already submitted feedback for this meal today.',
		)

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

	def test_cannot_create_duplicate_complaint_for_same_meal_on_same_day(self):
		Complaint.objects.create(
			raised_by=self.student,
			mess=self.mess,
			coupon_meal=CouponMeal.BREAKFAST,
			complaint_type='Food Quality',
			photo=SimpleUploadedFile('complaint-a.jpg', b'filecontent', content_type='image/jpeg'),
			description='First breakfast complaint.',
		)

		image_buffer = BytesIO()
		Image.new('RGB', (1, 1), color='white').save(image_buffer, format='PNG')
		photo = SimpleUploadedFile('complaint-b.png', image_buffer.getvalue(), content_type='image/png')

		response = self.client.post(
			reverse('complaint-list-create'),
			{
				'raised_by_id': self.student.user_id,
				'hostel_id': self.mess.hostel_id,
				'coupon_meal': CouponMeal.BREAKFAST,
				'complaint_type': 'Hygiene',
				'photo': photo,
				'description': 'Second breakfast complaint.',
			},
		)

		self.assertEqual(response.status_code, 400)
		self.assertEqual(
			response.data['detail'][0],
			'This user has already submitted a complaint for this meal today.',
		)

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

	def test_feedback_daily_summary_returns_average_and_rating_count_per_meal(self):
		same_hostel_second_student = Student.objects.create(
			name='Third API Student',
			email='api.student3@example.com',
			role=UserRole.STUDENT,
			student_id='STU202',
			mess=self.mess,
		)
		second_mess = Mess.objects.create(
			name='Hostel 2 Mess',
			hostel_id='H2',
		)
		second_student = Student.objects.create(
			name='Second API Student',
			email='api.student2@example.com',
			role=UserRole.STUDENT,
			student_id='STU201',
			mess=second_mess,
		)

		Feedback.objects.create(
			raised_by=self.student,
			coupon_meal=CouponMeal.BREAKFAST,
			rating=4,
			description='Nice breakfast.',
		)
		Feedback.objects.create(
			raised_by=same_hostel_second_student,
			coupon_meal=CouponMeal.BREAKFAST,
			rating=2,
			description='Average breakfast.',
		)
		Feedback.objects.create(
			raised_by=second_student,
			coupon_meal=CouponMeal.DINNER,
			rating=5,
			description='Great dinner.',
		)

		response = self.client.get(reverse('feedback-daily-summary'))

		self.assertEqual(response.status_code, 200)
		self.assertEqual(len(response.data), 2)

		hostel_one_summary = next(item for item in response.data if item['hostel_id'] == 'H1')
		breakfast_summary = next(meal for meal in hostel_one_summary['meals'] if meal['meal'] == CouponMeal.BREAKFAST)
		lunch_summary = next(meal for meal in hostel_one_summary['meals'] if meal['meal'] == CouponMeal.LUNCH)

		self.assertEqual(breakfast_summary['average_rating'], 3.0)
		self.assertEqual(breakfast_summary['rated_count'], 2)
		self.assertIsNone(lunch_summary['average_rating'])
		self.assertEqual(lunch_summary['rated_count'], 0)

		hostel_two_summary = next(item for item in response.data if item['hostel_id'] == 'H2')
		dinner_summary = next(meal for meal in hostel_two_summary['meals'] if meal['meal'] == CouponMeal.DINNER)

		self.assertEqual(dinner_summary['average_rating'], 5.0)
		self.assertEqual(dinner_summary['rated_count'], 1)

	def test_feedback_daily_summary_validates_date_query_param(self):
		response = self.client.get(reverse('feedback-daily-summary'), {'date': '16-04-2026'})

		self.assertEqual(response.status_code, 400)
		self.assertIn('YYYY-MM-DD', response.data['detail'])
