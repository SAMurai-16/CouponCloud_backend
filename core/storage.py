import json
import mimetypes
import os
import posixpath
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.files.storage import FileSystemStorage, Storage
from django.utils.deconstruct import deconstructible


@deconstructible
class BaseSupabaseStorage(Storage):
    bucket_setting = ""
    path_prefix_setting = ""
    public = True

    def __init__(self):
        self.local_storage = FileSystemStorage(location=settings.MEDIA_ROOT, base_url=settings.MEDIA_URL)

    @property
    def bucket_name(self):
        return getattr(settings, self.bucket_setting, "")

    @property
    def path_prefix(self):
        return getattr(settings, self.path_prefix_setting, "").strip("/")

    @property
    def enabled(self):
        return bool(settings.SUPABASE_URL and settings.SUPABASE_STORAGE_KEY and self.bucket_name)

    def _clean_name(self, name):
        normalized = str(name).replace("\\", "/").lstrip("/")
        if self.path_prefix:
            normalized = posixpath.join(self.path_prefix, normalized)
        return normalized

    def _public_url(self, name):
        quoted_name = quote(name, safe="/")
        quoted_bucket = quote(self.bucket_name, safe="")
        return f"{settings.SUPABASE_URL}/storage/v1/object/public/{quoted_bucket}/{quoted_name}"

    def _object_url(self, name):
        quoted_bucket = quote(self.bucket_name, safe="")
        quoted_name = quote(name, safe="/")
        return f"{settings.SUPABASE_URL}/storage/v1/object/{quoted_bucket}/{quoted_name}"

    def _request(self, method, url, *, data=None, headers=None, timeout=30):
        request = Request(url, data=data, method=method, headers=headers or {})
        with urlopen(request, timeout=timeout) as response:
            return response.read()

    def _save(self, name, content):
        if not self.enabled:
            return self.local_storage._save(name, content)

        clean_name = self._clean_name(name)
        content.open("rb")
        payload = content.read()
        content_type = getattr(content, "content_type", None) or mimetypes.guess_type(clean_name)[0] or "application/octet-stream"
        try:
            self._request(
                "POST",
                self._object_url(clean_name),
                data=payload,
                headers={
                    "apikey": settings.SUPABASE_STORAGE_KEY,
                    "Authorization": f"Bearer {settings.SUPABASE_STORAGE_KEY}",
                    "Content-Type": content_type,
                    "x-upsert": "false",
                },
            )
        except HTTPError as exc:
            raise ImproperlyConfigured(
                f"Supabase Storage upload failed with HTTP {exc.code} for bucket '{self.bucket_name}'."
            ) from exc
        except URLError as exc:
            raise ImproperlyConfigured(
                f"Supabase Storage upload failed for bucket '{self.bucket_name}' due to a network error."
            ) from exc
        return clean_name

    def delete(self, name):
        if not name:
            return

        if not self.enabled:
            self.local_storage.delete(name)
            return

        try:
            self._request(
                "DELETE",
                self._object_url(self._clean_name(name)),
                headers={
                    "apikey": settings.SUPABASE_STORAGE_KEY,
                    "Authorization": f"Bearer {settings.SUPABASE_STORAGE_KEY}",
                },
            )
        except Exception:
            return

    def exists(self, name):
        if not self.enabled:
            return self.local_storage.exists(name)
        return False

    def get_available_name(self, name, max_length=None):
        if not self.enabled:
            return self.local_storage.get_available_name(name, max_length=max_length)

        clean_name = self._clean_name(name)
        directory, filename = posixpath.split(clean_name)
        stem, extension = os.path.splitext(filename)
        unique_name = f"{stem}-{uuid.uuid4().hex}{extension}"
        candidate = posixpath.join(directory, unique_name) if directory else unique_name
        if max_length and len(candidate) > max_length:
            overflow = len(candidate) - max_length
            stem = stem[:-overflow] if overflow < len(stem) else uuid.uuid4().hex
            unique_name = f"{stem}-{uuid.uuid4().hex}{extension}"
            candidate = posixpath.join(directory, unique_name) if directory else unique_name
        return candidate

    def open(self, name, mode="rb"):
        if not self.enabled:
            return self.local_storage.open(name, mode)
        raise NotImplementedError("Supabase-backed files should be accessed via their URL.")

    def path(self, name):
        if not self.enabled:
            return self.local_storage.path(name)
        raise NotImplementedError("Supabase-backed files do not have a local filesystem path.")

    def size(self, name):
        if not self.enabled:
            return self.local_storage.size(name)
        raise NotImplementedError("Remote file size lookups are not implemented.")

    def url(self, name):
        if not name:
            return ""
        if not self.enabled:
            return self.local_storage.url(name)
        return self._public_url(self._clean_name(name))


@deconstructible
class PublicSupabaseStorage(BaseSupabaseStorage):
    bucket_setting = "SUPABASE_PUBLIC_BUCKET"
    path_prefix_setting = "SUPABASE_PUBLIC_PATH_PREFIX"
    public = True


@deconstructible
class PrivateQrSupabaseStorage(BaseSupabaseStorage):
    bucket_setting = "SUPABASE_QR_BUCKET"
    path_prefix_setting = "SUPABASE_QR_PATH_PREFIX"
    public = False

    def signed_url(self, name, expires_in=None):
        if not name:
            return ""
        if not self.enabled:
            return self.local_storage.url(name)

        clean_name = self._clean_name(name)
        expires_in = expires_in or settings.SUPABASE_QR_SIGNED_URL_TTL
        quoted_bucket = quote(self.bucket_name, safe="")
        quoted_name = quote(clean_name, safe="/")
        sign_url = f"{settings.SUPABASE_URL}/storage/v1/object/sign/{quoted_bucket}/{quoted_name}"

        try:
            raw_response = self._request(
                "POST",
                sign_url,
                data=json.dumps({"expiresIn": int(expires_in)}).encode("utf-8"),
                headers={
                    "apikey": settings.SUPABASE_STORAGE_KEY,
                    "Authorization": f"Bearer {settings.SUPABASE_STORAGE_KEY}",
                    "Content-Type": "application/json",
                },
            )
        except HTTPError as exc:
            raise ImproperlyConfigured(
                f"Supabase signed URL generation failed with HTTP {exc.code} for bucket '{self.bucket_name}'."
            ) from exc
        except URLError as exc:
            raise ImproperlyConfigured(
                f"Supabase signed URL generation failed for bucket '{self.bucket_name}' due to a network error."
            ) from exc

        payload = json.loads(raw_response.decode("utf-8"))
        signed_url = payload.get("signedURL") or payload.get("signedUrl")
        if not signed_url:
            raise ImproperlyConfigured("Supabase signed URL response did not include a signed URL.")

        if signed_url.startswith("http://") or signed_url.startswith("https://"):
            return signed_url

        # Supabase can return relative paths like /object/sign/... without
        # the /storage/v1 prefix. Normalize to a full, fetchable URL.
        if signed_url.startswith("/storage/v1/"):
            return f"{settings.SUPABASE_URL}{signed_url}"
        if signed_url.startswith("/object/"):
            return f"{settings.SUPABASE_URL}/storage/v1{signed_url}"
        if signed_url.startswith("object/"):
            return f"{settings.SUPABASE_URL}/storage/v1/{signed_url}"

        return f"{settings.SUPABASE_URL}/{signed_url.lstrip('/')}"

    def url(self, name):
        return self.signed_url(name)


public_media_storage = PublicSupabaseStorage()
private_qr_storage = PrivateQrSupabaseStorage()
