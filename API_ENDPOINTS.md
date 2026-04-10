# Coupon Cloud Backend API Endpoints

Base URL (local):
- `http://127.0.0.1:8000/`

Auth model:
- Login creates a Django session cookie (`sessionid`).
- Protected endpoint currently: `GET /coupons/`.
- For web clients, send requests with credentials enabled so cookies are included.

---

## 1) Health Check

### `GET /`
- Auth: Not required
- Request JSON: None

---

## 2) Auth

### `POST /signup/`
- Auth: Not required
- Request JSON (student):

```json
{
  "name": "Rahul Sharma",
  "email": "rahul@example.com",
  "password": "StrongPass123",
  "role": "student",
  "student_id": "STU1001",
  "hostel_id": "H1"
}
```

- Request JSON (staff):

```json
{
  "name": "Anita Verma",
  "email": "anita@example.com",
  "password": "StrongPass123",
  "role": "staff",
  "staff_id": "STA2001",
  "hostel_id": "H1"
}
```

### `POST /login/`
- Auth: Not required
- Request JSON:

```json
{
  "email": "rahul@example.com",
  "password": "StrongPass123"
}
```

---

## 3) Students

### `GET /students/`
- Auth: Not required
- Request JSON: None

### `GET /students/{student_id}/`
- Auth: Not required
- Path param: `student_id`
- Request JSON: None

---

## 4) Coupons

### `GET /coupons/`
- Auth: Required (session cookie)
- Request JSON: None

### `GET /coupons/{coupon_id}/qr/`
- Auth: Not required
- Path param: `coupon_id` (example format: `20260409-H1-STU1001-B`)
- Request JSON: None

### `POST /coupons/verify/`
- Auth: Not required
- Request JSON:

```json
{
  "qr_payload": "4b03ad4f-5fd8-4b73-ab08-08d18fb8fe2c"
}
```

---

## 5) Coupon Exchange Requests

### `GET /coupon-exchange-requests/`
- Auth: Required as authenticated student
- Request JSON: None
- Response: List of all coupon exchange requests received by the authenticated student, ordered by most recent first

Example response:
```json
[
  {
    "id": 1,
    "coupon": {
      "coupon_id": "20260409-H1-STU1001-L",
      "student": 5,
      "hostel_id": "H1",
      "coupon_meal": "L",
      "coupon_date": "2026-04-09",
      "valid_till": "2026-04-09T14:00:00+05:30",
      "qr_payload": "4b03ad4f-5fd8-4b73-ab08-08d18fb8fe2c",
      "qr_image_url": "http://127.0.0.1:8000/media/coupon_qr/20260409-H1-STU1001-L.png"
    },
    "requested_by": {
      "user_id": 5,
      "name": "Rahul Sharma",
      "email": "rahul@example.com",
      "role": "student",
      "student_id": "STU1001",
      "mess_name": "Mess H1",
      "hostel_id": "H1"
    },
    "requested_to": {
      "user_id": 6,
      "name": "Priya Singh",
      "email": "priya@example.com",
      "role": "student",
      "student_id": "STU1002",
      "mess_name": "Mess H1",
      "hostel_id": "H1"
    },
    "message": "Please take this lunch coupon.",
    "status": "pending",
    "requested_at": "2026-04-09T10:30:00Z",
    "responded_at": null
  }
]
```

### `POST /coupon-exchange-requests/`
- Auth: Required as authenticated student (enforced in serializer/view logic)
- Request JSON:

```json
{
  "coupon_id": "20260409-H1-STU1001-L",
  "requested_to_student_id": "STU1002",
  "message": "Please take this lunch coupon."
}
```

### `POST /coupon-exchange-requests/{exchange_id}/accept/`
- Auth: Required as authenticated recipient student
- Path param: `exchange_id`
- Request JSON: Empty body

```json
{}
```

### `POST /coupon-exchange-requests/{exchange_id}/reject/`
- Auth: Required as authenticated recipient student
- Path param: `exchange_id`
- Request JSON: Empty body

```json
{}
```

---

## 6) Mess Menus

### `GET /mess-menus/`
- Auth: Not required
- Optional query params:
  - `hostel_id`
  - `day_of_week` (`MON`, `TUE`, `WED`, `THU`, `FRI`, `SAT`, `SUN`)
  - `meal` (`B`, `L`, `S`, `D`)
- Request JSON: None

### `POST /mess-menus/`
- Auth: Not required
- Request JSON:

```json
{
  "hostel_id": "H1",
  "day_of_week": "MON",
  "meal": "L",
  "items": [
    { "name": "Rice", "display_order": 1 },
    { "name": "Dal", "display_order": 2 }
  ]
}
```

### `GET /mess-menus/{menu_id}/`
- Auth: Not required
- Path param: `menu_id`
- Request JSON: None

### `GET /messes/names/`
- Auth: Not required
- Request JSON: None

---

## 7) Feedback

### `GET /feedbacks/`
- Auth: Not required
- Optional query params:
  - `raised_by_id`
  - `coupon_meal` (`B`, `L`, `S`, `D`)
  - `hostel_id`
- Request JSON: None

### `POST /feedbacks/`
- Auth: Not required
- Request JSON:

```json
{
  "raised_by_id": 12,
  "coupon_meal": "D",
  "rating": 5,
  "description": "Very good dinner."
}
```

Notes:
- `hostel_id` is auto-derived by backend from the selected user's linked mess (student/staff).
- Rating must be between 1 and 5.

---

## 8) Complaints

### `GET /complaints/`
- Auth: Not required
- Optional query params:
  - `raised_by_id`
  - `hostel_id`
  - `coupon_meal` (`B`, `L`, `S`, `D`)
- Request JSON: None

### `POST /complaints/`
- Auth: Not required
- Content type: `multipart/form-data` (because `photo` is an uploaded file)
- Required fields:
  - `raised_by_id` (integer user id)
  - `hostel_id` (maps to mess)
  - `coupon_meal` (`B`, `L`, `S`, `D`)
  - `complaint_type`
  - `photo` (file)
  - `description`

Example (conceptual fields):

```json
{
  "raised_by_id": 12,
  "hostel_id": "H1",
  "coupon_meal": "B",
  "complaint_type": "Food Quality",
  "description": "Breakfast quality was poor."
}
```

---

## Enum Summary

- `role`: `student`, `staff`
- `coupon_meal` / `meal`:
  - `B` = Breakfast
  - `L` = Lunch
  - `S` = Snacks
  - `D` = Dinner
- `day_of_week`: `MON`, `TUE`, `WED`, `THU`, `FRI`, `SAT`, `SUN`
