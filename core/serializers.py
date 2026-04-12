from django.contrib.auth import authenticate
from django.db import IntegrityError, transaction
from zoneinfo import ZoneInfo
from rest_framework import serializers

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
    UserRole,
)


class StudentProfileSerializer(serializers.ModelSerializer):
    mess_name = serializers.CharField(source='mess.name', read_only=True)
    hostel_id = serializers.CharField(source='mess.hostel_id', read_only=True)

    class Meta:
        model = Student
        fields = ['student_id', 'mess_name', 'hostel_id']


class StudentSerializer(serializers.ModelSerializer):
    mess_name = serializers.CharField(source='mess.name', read_only=True)
    hostel_id = serializers.CharField(source='mess.hostel_id', read_only=True)

    class Meta:
        model = Student
        fields = ['user_id', 'name', 'email', 'role', 'student_id', 'mess_name', 'hostel_id']


class CouponSerializer(serializers.ModelSerializer):
    qr_image_url = serializers.SerializerMethodField()
    valid_till = serializers.SerializerMethodField()

    class Meta:
        model = Coupon
        fields = [
            'coupon_id',
            'student',
            'hostel_id',
            'coupon_meal',
            'coupon_date',
            'valid_till',
            'qr_payload',
            'qr_image_url',
        ]

    def get_qr_image_url(self, obj):
        if not obj.qr_image:
            return None

        request = self.context.get('request')
        url = obj.qr_image.url
        return request.build_absolute_uri(url) if request else url

    def get_valid_till(self, obj):
        if not obj.valid_till:
            return None

        return obj.valid_till.astimezone(ZoneInfo('Asia/Kolkata')).isoformat()


class CouponExchangeRequestSerializer(serializers.ModelSerializer):
    coupon = CouponSerializer(read_only=True)
    requested_by = StudentSerializer(read_only=True)
    requested_to = StudentSerializer(read_only=True)

    class Meta:
        model = CouponTransferRequest
        fields = [
            'id',
            'coupon',
            'requested_by',
            'requested_to',
            'message',
            'status',
            'requested_at',
            'responded_at',
        ]


class CouponExchangeCreateSerializer(serializers.Serializer):
    coupon_id = serializers.CharField(max_length=50)
    requested_to_student_id = serializers.CharField(max_length=50)
    message = serializers.CharField(required=False, allow_blank=True, default='')

    def validate(self, attrs):
        request = self.context['request']

        if not request.user.is_authenticated or not hasattr(request.user, 'student'):
            raise serializers.ValidationError({'detail': 'Only authenticated students can request exchanges.'})

        try:
            coupon = Coupon.objects.select_related('student', 'student__mess').get(coupon_id=attrs['coupon_id'])
        except Coupon.DoesNotExist as exc:
            raise serializers.ValidationError({'coupon_id': 'Coupon not found.'}) from exc

        requester = request.user.student
        if coupon.student_id != requester.user_id:
            raise serializers.ValidationError({'coupon_id': 'You can only exchange your own coupon.'})

        if CouponTransferRequest.objects.filter(coupon=coupon, status=CouponTransferStatus.PENDING).exists():
            raise serializers.ValidationError({'coupon_id': 'This coupon already has a pending exchange request.'})

        try:
            requested_to = Student.objects.select_related('mess').get(student_id=attrs['requested_to_student_id'])
        except Student.DoesNotExist as exc:
            raise serializers.ValidationError({'requested_to_student_id': 'Recipient student not found.'}) from exc

        if requested_to.user_id == requester.user_id:
            raise serializers.ValidationError({'requested_to_student_id': 'You cannot exchange a coupon with yourself.'})

        if requested_to.mess.hostel_id == coupon.hostel_id:
            raise serializers.ValidationError(
                {'requested_to_student_id': 'Coupon exchange must be between students of different hostels.'}
            )

        try:
            requested_to_coupon = Coupon.objects.select_related('student', 'student__mess').get(
                student=requested_to,
                coupon_meal=coupon.coupon_meal,
                coupon_date=coupon.coupon_date,
            )
        except Coupon.DoesNotExist as exc:
            raise serializers.ValidationError(
                {'requested_to_student_id': 'Recipient does not have a matching coupon for this meal and date.'}
            ) from exc

        attrs['coupon'] = coupon
        attrs['requested_by'] = requester
        attrs['requested_to'] = requested_to
        attrs['requested_to_coupon'] = requested_to_coupon
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        coupon = validated_data['coupon']
        transfer_request = CouponTransferRequest.objects.create(
            coupon=coupon,
            requested_by=validated_data['requested_by'],
            requested_to=validated_data['requested_to'],
            message=validated_data.get('message', ''),
        )
        return transfer_request


class CouponExchangeActionSerializer(serializers.Serializer):
    detail = serializers.CharField(read_only=True)

    def validate_action(self, value):
        if value not in {CouponTransferStatus.ACCEPTED, CouponTransferStatus.REJECTED}:
            raise serializers.ValidationError('Invalid action.')
        return value


class MessMenuItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = MessMenuItem
        fields = ['id', 'name', 'display_order']


class MessSerializer(serializers.ModelSerializer):
    class Meta:
        model = Mess
        fields = ['id', 'name', 'hostel_id']


class MessMenuSerializer(serializers.ModelSerializer):
    mess = MessSerializer(read_only=True)
    items = MessMenuItemSerializer(many=True, read_only=True)

    class Meta:
        model = MessMenu
        fields = ['id', 'mess', 'day_of_week', 'meal', 'items']


class MessMenuCreateSerializer(serializers.Serializer):
    hostel_id = serializers.CharField(max_length=50)
    day_of_week = serializers.ChoiceField(choices=MessMenu._meta.get_field('day_of_week').choices)
    meal = serializers.ChoiceField(choices=MessMenu._meta.get_field('meal').choices)
    items = MessMenuItemSerializer(many=True)

    def validate_hostel_id(self, value):
        try:
            mess = Mess.objects.get(hostel_id=value)
        except Mess.DoesNotExist as exc:
            raise serializers.ValidationError('Mess not found for the provided hostel_id.') from exc
        except Mess.MultipleObjectsReturned as exc:
            raise serializers.ValidationError('Multiple mess rows found for this hostel_id.') from exc
        return mess

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError('At least one menu item is required.')
        return value

    def validate(self, attrs):
        mess = attrs['hostel_id']
        day_of_week = attrs['day_of_week']
        meal = attrs['meal']

        if MessMenu.objects.filter(mess=mess, day_of_week=day_of_week, meal=meal).exists():
            raise serializers.ValidationError(
                {'detail': 'A menu already exists for this mess, day, and meal.'}
            )

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        mess = validated_data['hostel_id']
        items_data = validated_data.pop('items')

        menu = MessMenu.objects.create(
            mess=mess,
            day_of_week=validated_data['day_of_week'],
            meal=validated_data['meal'],
        )

        MessMenuItem.objects.bulk_create(
            [MessMenuItem(menu=menu, **item_data) for item_data in items_data]
        )

        return menu


class StaffProfileSerializer(serializers.ModelSerializer):
    mess_name = serializers.CharField(source='mess.name', read_only=True)
    hostel_id = serializers.CharField(source='mess.hostel_id', read_only=True)

    class Meta:
        model = Staff
        fields = ['staff_id', 'mess_name', 'hostel_id']


class AuthUserSerializer(serializers.ModelSerializer):
    profile = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['user_id', 'name', 'email', 'role', 'profile']

    def get_profile(self, obj):
        if obj.role == UserRole.STUDENT and hasattr(obj, 'student'):
            return StudentProfileSerializer(obj.student).data
        if obj.role == UserRole.STAFF and hasattr(obj, 'staff'):
            return StaffProfileSerializer(obj.staff).data
        return None


class SignupSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    role = serializers.ChoiceField(choices=UserRole.choices)
    student_id = serializers.CharField(max_length=50, required=False, allow_blank=False)
    staff_id = serializers.CharField(max_length=50, required=False, allow_blank=False)
    hostel_id = serializers.CharField(max_length=50)

    def validate_hostel_id(self, value):
        try:
            mess = Mess.objects.get(hostel_id=value)
        except Mess.DoesNotExist as exc:
            raise serializers.ValidationError('Mess not found for the provided hostel_id.') from exc
        except Mess.MultipleObjectsReturned as exc:
            raise serializers.ValidationError('Multiple mess rows found for this hostel_id.') from exc
        return mess

    def validate(self, attrs):
        role = attrs['role']

        if User.objects.filter(email=attrs['email']).exists():
            raise serializers.ValidationError({'email': 'A user with this email already exists.'})

        if role == UserRole.STUDENT and not attrs.get('student_id'):
            raise serializers.ValidationError({'student_id': 'This field is required for student accounts.'})

        if role == UserRole.STAFF and not attrs.get('staff_id'):
            raise serializers.ValidationError({'staff_id': 'This field is required for staff accounts.'})

        if role == UserRole.STUDENT and Student.objects.filter(student_id=attrs.get('student_id')).exists():
            raise serializers.ValidationError({'student_id': 'A student with this student_id already exists.'})

        if role == UserRole.STAFF and Staff.objects.filter(staff_id=attrs.get('staff_id')).exists():
            raise serializers.ValidationError({'staff_id': 'A staff user with this staff_id already exists.'})

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        role = validated_data.pop('role')
        password = validated_data.pop('password')
        student_id = validated_data.pop('student_id', None)
        staff_id = validated_data.pop('staff_id', None)
        mess = validated_data.pop('hostel_id')

        try:
            if role == UserRole.STUDENT:
                user = Student.objects.create(
                    **validated_data,
                    student_id=student_id,
                    mess=mess,
                )
            elif role == UserRole.STAFF:
                user = Staff.objects.create(
                    **validated_data,
                    staff_id=staff_id,
                    mess=mess,
                )
            else:
                raise serializers.ValidationError({'role': 'Invalid role.'})
        except IntegrityError as exc:
            error_message = str(exc)
            if 'core_student.student_id' in error_message:
                raise serializers.ValidationError({'student_id': 'A student with this student_id already exists.'}) from exc
            if 'core_staff.staff_id' in error_message:
                raise serializers.ValidationError({'staff_id': 'A staff user with this staff_id already exists.'}) from exc
            if 'core_user.email' in error_message:
                raise serializers.ValidationError({'email': 'A user with this email already exists.'}) from exc
            raise serializers.ValidationError({'detail': 'Could not create account due to a data conflict.'}) from exc

        user.set_password(password)
        user.save(update_fields=['password'])
        return user


class LoginSerializer(serializers.Serializer):
    student_id = serializers.CharField(max_length=50)
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        try:
            student = Student.objects.get(student_id=attrs['student_id'])
        except Student.DoesNotExist as exc:
            raise serializers.ValidationError({'detail': 'Invalid student ID or password.'}) from exc

        user = authenticate(
            request=self.context.get('request'),
            email=student.email,
            password=attrs['password'],
        )
        if user is None:
            raise serializers.ValidationError({'detail': 'Invalid student ID or password.'})

        attrs['user'] = user
        return attrs


class FeedbackSerializer(serializers.ModelSerializer):
    raised_by = AuthUserSerializer(read_only=True)
    raised_by_id = serializers.PrimaryKeyRelatedField(
        source='raised_by', queryset=User.objects.all(), write_only=True
    )

    def validate(self, attrs):
        raised_by = attrs.get('raised_by')

        if hasattr(raised_by, 'student'):
            attrs['hostel_id'] = raised_by.student.hostel_id
        elif hasattr(raised_by, 'staff'):
            attrs['hostel_id'] = raised_by.staff.hostel_id
        else:
            raise serializers.ValidationError(
                {'raised_by_id': 'Selected user must be linked to a mess.'}
            )

        return attrs

    class Meta:
        model = Feedback
        fields = [
            'id',
            'raised_by',
            'raised_by_id',
            'hostel_id',
            'coupon_meal',
            'rating',
            'description',
        ]


class ComplaintSerializer(serializers.ModelSerializer):
    raised_by = AuthUserSerializer(read_only=True)
    raised_by_id = serializers.PrimaryKeyRelatedField(
        source='raised_by', queryset=User.objects.all(), write_only=True
    )
    mess = MessSerializer(read_only=True)
    hostel_id = serializers.CharField(write_only=True)

    def validate_hostel_id(self, value):
        try:
            mess = Mess.objects.get(hostel_id=value)
        except Mess.DoesNotExist as exc:
            raise serializers.ValidationError('Mess not found for the provided hostel_id.') from exc
        except Mess.MultipleObjectsReturned as exc:
            raise serializers.ValidationError('Multiple mess rows found for this hostel_id.') from exc
        return mess

    def create(self, validated_data):
        validated_data['mess'] = validated_data.pop('hostel_id')
        return super().create(validated_data)

    class Meta:
        model = Complaint
        fields = [
            'id',
            'raised_by',
            'raised_by_id',
            'mess',
            'hostel_id',
            'coupon_meal',
            'complaint_type',
            'photo',
            'description',
        ]
