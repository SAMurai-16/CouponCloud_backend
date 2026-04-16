from django.urls import path

from .views import (
    ComplaintListCreateView,
    CouponQrView,
    CouponVerifyView,
    CouponExchangeAcceptView,
    CouponExchangeRejectView,
    CouponExchangeRequestCreateView,
    DailyMealRatingSummaryView,
    FeedbackListCreateView,
    health_check,
    LoginView,
    CouponListView,
    MessListView,
    MessNameListView,
    MessMenuDetailView,
    MessMenuListCreateView,
    SignupView,
    StudentDetailView,
    StudentListView,
)


urlpatterns = [
    path('', health_check, name='health-check'),
    path('signup/', SignupView.as_view(), name='signup'),
    path('login/', LoginView.as_view(), name='login'),
    path('students/', StudentListView.as_view(), name='student-list'),
    path('students/<str:student_id>/', StudentDetailView.as_view(), name='student-detail'),
    path('coupons/', CouponListView.as_view(), name='coupon-list'),
    path('coupons/<str:coupon_id>/qr/', CouponQrView.as_view(), name='coupon-qr'),
    path('coupons/verify/', CouponVerifyView.as_view(), name='coupon-verify'),
    path('coupon-exchange-requests/', CouponExchangeRequestCreateView.as_view(), name='coupon-exchange-request-create'),
    path(
        'coupon-exchange-requests/<int:exchange_id>/accept/',
        CouponExchangeAcceptView.as_view(),
        name='coupon-exchange-request-accept',
    ),
    path(
        'coupon-exchange-requests/<int:exchange_id>/reject/',
        CouponExchangeRejectView.as_view(),
        name='coupon-exchange-request-reject',
    ),
    path('mess-menus/', MessMenuListCreateView.as_view(), name='mess-menu-list-create'),
    path('mess-menus/<int:menu_id>/', MessMenuDetailView.as_view(), name='mess-menu-detail'),
    path('messes/names/', MessNameListView.as_view(), name='mess-name-list'),
    path('mess/', MessListView.as_view(), name='mess-list'),
    path('feedbacks/', FeedbackListCreateView.as_view(), name='feedback-list-create'),
    path('feedbacks/daily-summary/', DailyMealRatingSummaryView.as_view(), name='feedback-daily-summary'),
    path('complaints/', ComplaintListCreateView.as_view(), name='complaint-list-create'),
]
