from django.contrib import admin

from .models import (
	Complaint,
	Coupon,
	CouponTransferRequest,
	CouponTransferStatus,
	Feedback,
	Mess,
	MessMenu,
	MessMenuItem,
	Staff,
	Student,
	User,
)


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
	list_display = ('user_id', 'name', 'email', 'role', 'is_staff', 'is_active')
	search_fields = ('name', 'email')
	list_filter = ('role', 'is_staff', 'is_active')


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
	list_display = ('user_id', 'name', 'email', 'student_id', 'hostel_id')
	search_fields = ('name', 'email', 'student_id')


@admin.register(Staff)
class StaffAdmin(admin.ModelAdmin):
	list_display = ('user_id', 'name', 'email', 'staff_id', 'hostel_id')
	search_fields = ('name', 'email', 'staff_id')


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
	list_display = ('coupon_id', 'student', 'hostel_id', 'coupon_meal', 'coupon_date')
	search_fields = ('coupon_id', 'student__student_id', 'student__name')
	list_filter = ('coupon_meal', 'coupon_date', 'hostel_id')


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
	list_display = ('id', 'raised_by', 'coupon_meal', 'rating')
	search_fields = ('description', 'raised_by__name', 'raised_by__email', 'coupon_meal')


@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):
	list_display = ('id', 'raised_by', 'mess', 'coupon_meal', 'complaint_type')
	search_fields = (
		'complaint_type',
		'description',
		'raised_by__name',
		'raised_by__email',
		'mess__name',
		'mess__hostel_id',
		'coupon_meal',
	)


@admin.register(CouponTransferRequest)
class CouponExchangeRequestAdmin(admin.ModelAdmin):
	list_display = ('id', 'coupon', 'requested_by', 'requested_to', 'status', 'requested_at', 'responded_at')
	search_fields = (
		'coupon__coupon_id',
		'coupon__student__student_id',
		'requested_by__student_id',
		'requested_to__student_id',
		'message',
	)
	list_filter = ('status', 'requested_at', 'responded_at')

	def save_model(self, request, obj, form, change):
		if change:
			current_obj = CouponTransferRequest.objects.select_related('coupon', 'requested_by', 'requested_to').get(pk=obj.pk)

			if current_obj.status == CouponTransferStatus.PENDING and obj.status == CouponTransferStatus.ACCEPTED:
				current_obj.accept()
				return

			if current_obj.status == CouponTransferStatus.PENDING and obj.status == CouponTransferStatus.REJECTED:
				current_obj.reject()
				return

		super().save_model(request, obj, form, change)


class MessMenuItemInline(admin.TabularInline):
	model = MessMenuItem
	extra = 1


@admin.register(Mess)
class MessAdmin(admin.ModelAdmin):
	list_display = ('id', 'name', 'hostel_id')
	search_fields = ('name', 'hostel_id')


@admin.register(MessMenu)
class MessMenuAdmin(admin.ModelAdmin):
	list_display = ('mess', 'day_of_week', 'meal')
	search_fields = ('mess__name', 'mess__hostel_id')
	list_filter = ('day_of_week', 'meal', 'mess__hostel_id')
	inlines = [MessMenuItemInline]
