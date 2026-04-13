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
class SupabaseStorage(Storage):
    def __init__(self):
        self.local_storage = FileSystemStorage(location=settings.MEDIA_ROOT, base_url=settings.MEDIA_URL)

    @property
    def enabled(self):
        return bool(
            settings.SUPABASE_URL
            and settings.SUPABASE_STORAGE_KEY
            and settings.SUPABASE_STORAGE_BUCKET
        )

    def _clean_name(self, name):
        normalized = str(name).replace("\\", "/").lstrip("/")
        prefix = settings.SUPABASE_STORAGE_PATH_PREFIX.strip("/")
        if prefix:
            normalized = posixpath.join(prefix, normalized)
        return normalized

    def _public_url(self, name):
        quoted_name = quote(name, safe="/")
        return (
            f"{settings.SUPABASE_URL}/storage/v1/object/public/"
            f"{settings.SUPABASE_STORAGE_BUCKET}/{quoted_name}"
        )

    def _object_url(self, name):
        quoted_bucket = quote(settings.SUPABASE_STORAGE_BUCKET, safe="")
        quoted_name = quote(name, safe="/")
        return f"{settings.SUPABASE_URL}/storage/v1/object/{quoted_bucket}/{quoted_name}"

    def _save(self, name, content):
        if not self.enabled:
            return self.local_storage._save(name, content)

        clean_name = self._clean_name(name)
        content.open("rb")
        payload = content.read()
        content_type = getattr(content, "content_type", None) or mimetypes.guess_type(clean_name)[0] or "application/octet-stream"
        try:
            request = Request(
                self._object_url(clean_name),
                data=payload,
                method="POST",
                headers={
                    "apikey": settings.SUPABASE_STORAGE_KEY,
                    "Authorization": f"Bearer {settings.SUPABASE_STORAGE_KEY}",
                    "Content-Type": content_type,
                    "x-upsert": "false",
                },
            )
            with urlopen(request, timeout=30) as response:
                response.read()
        except HTTPError as exc:
            raise ImproperlyConfigured(
                f"Supabase Storage upload failed with HTTP {exc.code}. "
                "Check SUPABASE_URL, SUPABASE_STORAGE_KEY, SUPABASE_STORAGE_BUCKET, "
                "bucket visibility, and Render deploy logs."
            ) from exc
        except URLError as exc:
            raise ImproperlyConfigured(
                "Supabase Storage upload failed due to a network error. "
                "Check outbound network access and SUPABASE_URL."
            ) from exc
        return clean_name

    def delete(self, name):
        if not name:
            return

        if not self.enabled:
            self.local_storage.delete(name)
            return

        clean_name = self._clean_name(name)
        request = Request(
            self._object_url(clean_name),
            method="DELETE",
            headers={
                "apikey": settings.SUPABASE_STORAGE_KEY,
                "Authorization": f"Bearer {settings.SUPABASE_STORAGE_KEY}",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                response.read()
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
