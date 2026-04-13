import uuid
from io import BytesIO
from datetime import datetime, time
from zoneinfo import ZoneInfo

import qrcode
from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.core.validators import MaxValueValidator, MinValueValidator
from django.core.files.base import ContentFile
from django.db import models
from django.db.models import Q
from django.utils import timezone

from .storage import private_qr_storage, public_media_storage


class UserRole(models.TextChoices):
	STUDENT = 'student', 'Student'
	STAFF = 'staff', 'Staff'


class CouponMeal(models.TextChoices):
	BREAKFAST = 'B', 'Breakfast'
	LUNCH = 'L', 'Lunch'
	SNACKS = 'S', 'Snacks'
	DINNER = 'D', 'Dinner'


class Weekday(models.TextChoices):
	MONDAY = 'MON', 'Monday'
	TUESDAY = 'TUE', 'Tuesday'
	WEDNESDAY = 'WED', 'Wednesday'
	THURSDAY = 'THU', 'Thursday'
	FRIDAY = 'FRI', 'Friday'
	SATURDAY = 'SAT', 'Saturday'
	SUNDAY = 'SUN', 'Sunday'


class UserManager(BaseUserManager):
	use_in_migrations = True

	def create_user(self, email, name, role, password=None, **extra_fields):
		if not email:
			raise ValueError('The email field must be set.')
		if not name:
			raise ValueError('The name field must be set.')
		if not role:
			raise ValueError('The role field must be set.')

		email = self.normalize_email(email)
		user = self.model(email=email, name=name, role=role, **extra_fields)
		user.set_password(password)
		user.save(using=self._db)
		return user

	def create_superuser(self, email, name, password=None, **extra_fields):
		extra_fields.setdefault('is_staff', True)
		extra_fields.setdefault('is_superuser', True)
		extra_fields.setdefault('role', UserRole.STAFF)

		if extra_fields.get('is_staff') is not True:
			raise ValueError('Superuser must have is_staff=True.')
		if extra_fields.get('is_superuser') is not True:
			raise ValueError('Superuser must have is_superuser=True.')

		return self.create_user(email=email, name=name, password=password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
	user_id = models.BigAutoField(primary_key=True)
	name = models.CharField(max_length=255)
	email = models.EmailField(unique=True)
	role = models.CharField(max_length=20, choices=UserRole.choices)
	is_staff = models.BooleanField(default=False)
	is_active = models.BooleanField(default=True)
	date_joined = models.DateTimeField(auto_now_add=True)

	objects = UserManager()

	USERNAME_FIELD = 'email'
	REQUIRED_FIELDS = ['name', 'role']

	def __str__(self):
		return f'{self.name} <{self.email}>'


class Student(User):
	student_id = models.CharField(max_length=50, unique=True)
	mess = models.ForeignKey('Mess', on_delete=models.PROTECT, related_name='students')

	@property
	def hostel_id(self):
		return self.mess.hostel_id

	def save(self, *args, **kwargs):
		self.role = UserRole.STUDENT
		self.is_staff = False
		super().save(*args, **kwargs)


class Staff(User):
	staff_id = models.CharField(max_length=50, unique=True)
	mess = models.ForeignKey('Mess', on_delete=models.PROTECT, related_name='staff_members')

	@property
	def hostel_id(self):
		return self.mess.hostel_id

	def save(self, *args, **kwargs):
		self.role = UserRole.STAFF
		self.is_staff = False
		super().save(*args, **kwargs)


class Mess(models.Model):
	name = models.CharField(max_length=255)
	hostel_id = models.CharField(max_length=50)

	def __str__(self):
		return f'{self.name} ({self.hostel_id})'


class MessMenu(models.Model):
	mess = models.ForeignKey(Mess, on_delete=models.CASCADE, related_name='menus')
	day_of_week = models.CharField(max_length=3, choices=Weekday.choices)
	meal = models.CharField(max_length=1, choices=CouponMeal.choices)

	class Meta:
		constraints = [
			models.UniqueConstraint(
				fields=['mess', 'day_of_week', 'meal'],
				name='unique_menu_per_mess_day_meal',
			),
		]

	def __str__(self):
		return f'{self.mess.name} - {self.day_of_week} - {self.meal}'


class MessMenuItem(models.Model):
	menu = models.ForeignKey(MessMenu, on_delete=models.CASCADE, related_name='items')
	name = models.CharField(max_length=255)
	display_order = models.PositiveIntegerField(default=1)

	class Meta:
		ordering = ['display_order', 'id']

	def __str__(self):
		return self.name


class Feedback(models.Model):
	raised_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='feedbacks')
	hostel_id = models.CharField(max_length=50, blank=True, default='', db_index=True)
	coupon_meal = models.CharField(max_length=1, choices=CouponMeal.choices)
	rating = models.PositiveSmallIntegerField(
		validators=[MinValueValidator(1), MaxValueValidator(5)]
	)
	description = models.TextField()

	def save(self, *args, **kwargs):
		if not self.hostel_id and self.raised_by_id:
			if hasattr(self.raised_by, 'student'):
				self.hostel_id = self.raised_by.student.hostel_id
			elif hasattr(self.raised_by, 'staff'):
				self.hostel_id = self.raised_by.staff.hostel_id
		super().save(*args, **kwargs)

	def __str__(self):
		return f'Feedback {self.id} - {self.coupon_meal} - {self.rating}/5'


class Complaint(models.Model):
	raised_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='complaints')
	mess = models.ForeignKey(Mess, on_delete=models.PROTECT, related_name='complaints')
	coupon_meal = models.CharField(max_length=1, choices=CouponMeal.choices)
	complaint_type = models.CharField(max_length=100)
	photo = models.ImageField(upload_to='complaints/', storage=public_media_storage)
	description = models.TextField()

	def __str__(self):
		return f'Complaint {self.id} - {self.coupon_meal} - {self.complaint_type}'


class Coupon(models.Model):
	student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='coupons')
	hostel_id = models.CharField(max_length=50)
	coupon_id = models.CharField(max_length=50, unique=True)
	coupon_meal = models.CharField(max_length=1, choices=CouponMeal.choices)
	coupon_date = models.DateField()
	valid_till = models.DateTimeField(null=True, blank=True)
	qr_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
	qr_payload = models.TextField(blank=True)
	qr_image = models.ImageField(upload_to='', blank=True, storage=private_qr_storage)

	VALID_TILL_BY_MEAL = {
		CouponMeal.BREAKFAST: time(hour=10, minute=0),
		CouponMeal.LUNCH: time(hour=14, minute=0),
		CouponMeal.SNACKS: time(hour=18, minute=30),
		CouponMeal.DINNER: time(hour=21, minute=0),
	}

	class Meta:
		constraints = [
			models.UniqueConstraint(
				fields=['student', 'hostel_id', 'coupon_meal', 'coupon_date'],
				name='unique_daily_coupon_per_student_meal_hostel',
			),
		]

	def build_qr_payload(self):
		return str(self.qr_token)

	def swap_with(self, other_coupon):
		if self.pk == other_coupon.pk:
			raise ValueError('Cannot exchange a coupon with itself.')

		self_original_student = self.student

		other_original_student = other_coupon.student

		other_coupon.student = self_original_student
		other_coupon.rotate_qr()
		other_coupon.save()
		other_coupon.ensure_qr_image()
		other_coupon.save(update_fields=['qr_payload', 'qr_image'])

		self.student = other_original_student
		self.rotate_qr()
		self.save()
		self.ensure_qr_image()
		self.save(update_fields=['qr_payload', 'qr_image'])

	def build_valid_till(self):
		meal_time = self.VALID_TILL_BY_MEAL.get(self.coupon_meal)
		if meal_time is None:
			raise ValueError('Invalid coupon meal for valid_till calculation.')

		ist = ZoneInfo('Asia/Kolkata')
		return datetime.combine(self.coupon_date, meal_time, tzinfo=ist)

	def generate_qr_image(self):
		qr = qrcode.QRCode(version=1, box_size=10, border=4)
		qr.add_data(self.qr_payload)
		qr.make(fit=True)

		image = qr.make_image(fill_color='black', back_color='white')
		buffer = BytesIO()
		image.save(buffer, format='PNG')
		filename = f'{self.coupon_id}.png'
		self.qr_image.save(filename, ContentFile(buffer.getvalue()), save=False)

	def ensure_qr_image(self, save=True):
		if not self.qr_payload:
			self.qr_payload = self.build_qr_payload()
		if not self.qr_image:
			self.generate_qr_image()
			if save:
				self.save(update_fields=['qr_payload', 'qr_image'])
		return self.qr_image

	def __str__(self):
		return f'{self.coupon_id} - {self.hostel_id} - {self.coupon_meal}'

	def save(self, *args, **kwargs):
		self.qr_payload = self.build_qr_payload()
		self.valid_till = self.build_valid_till()
		super().save(*args, **kwargs)

	def rotate_qr(self):
		if self.qr_image:
			self.qr_image.delete(save=False)
		self.qr_token = uuid.uuid4()
		self.qr_payload = self.build_qr_payload()
		self.qr_image = None

	@classmethod
	def build_coupon_id(cls, student, meal_code, coupon_date):
		return f'{coupon_date.strftime("%Y%m%d")}-{student.hostel_id}-{student.student_id}-{meal_code}'

	@classmethod
	def create_daily_coupons(cls, coupon_date=None):
		coupon_date = coupon_date or timezone.localdate()
		created_count = 0

		for student in Student.objects.all().order_by('student_id'):
			for meal_code, _ in CouponMeal.choices:
				coupon, created = cls.objects.get_or_create(
					student=student,
					hostel_id=student.hostel_id,
					coupon_meal=meal_code,
					coupon_date=coupon_date,
					defaults={
						'coupon_id': cls.build_coupon_id(student, meal_code, coupon_date),
					},
				)
				if created:
					created_count += 1
				if not coupon.qr_image:
					coupon.ensure_qr_image()

		return created_count

	@classmethod
	def create_daily_coupons_for_student(cls, student, coupon_date=None):
		coupon_date = coupon_date or timezone.localdate()
		created_count = 0

		for meal_code, _ in CouponMeal.choices:
			coupon, created = cls.objects.get_or_create(
				student=student,
				hostel_id=student.hostel_id,
				coupon_meal=meal_code,
				coupon_date=coupon_date,
				defaults={
					'coupon_id': cls.build_coupon_id(student, meal_code, coupon_date),
				},
			)
			if created:
				created_count += 1
			if not coupon.qr_image:
				coupon.ensure_qr_image()

		return created_count


class CouponTransferStatus(models.TextChoices):
	PENDING = 'pending', 'Pending'
	ACCEPTED = 'accepted', 'Accepted'
	REJECTED = 'rejected', 'Rejected'


class CouponTransferRequest(models.Model):
	coupon = models.ForeignKey(Coupon, on_delete=models.CASCADE, related_name='transfer_requests')
	requested_by = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='coupon_transfer_requests_sent')
	requested_to = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='coupon_transfer_requests_received')
	message = models.TextField(blank=True, default='')
	status = models.CharField(max_length=20, choices=CouponTransferStatus.choices, default=CouponTransferStatus.PENDING)
	requested_at = models.DateTimeField(auto_now_add=True)
	responded_at = models.DateTimeField(null=True, blank=True)

	class Meta:
		constraints = [
			models.UniqueConstraint(
				fields=['coupon'],
				condition=Q(status=CouponTransferStatus.PENDING),
				name='unique_pending_transfer_per_coupon',
			),
		]

	def accept(self):
		if self.status != CouponTransferStatus.PENDING:
			raise ValueError('Only pending exchange requests can be accepted.')

		recipient_coupon = Coupon.objects.select_related('student', 'student__mess').get(
			student=self.requested_to,
			coupon_meal=self.coupon.coupon_meal,
			coupon_date=self.coupon.coupon_date,
		)

		self.coupon.swap_with(recipient_coupon)
		self.status = CouponTransferStatus.ACCEPTED
		self.responded_at = timezone.now()
		self.save(update_fields=['status', 'responded_at'])

	def reject(self):
		if self.status != CouponTransferStatus.PENDING:
			raise ValueError('Only pending exchange requests can be rejected.')

		self.status = CouponTransferStatus.REJECTED
		self.responded_at = timezone.now()
		self.save(update_fields=['status', 'responded_at'])
