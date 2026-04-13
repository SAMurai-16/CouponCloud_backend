import mimetypes
import os
import posixpath
import uuid
from urllib.parse import quote

from django.conf import settings
from django.core.files.storage import FileSystemStorage, Storage
from django.utils.deconstruct import deconstructible

try:
    from supabase import create_client
except ImportError:  # pragma: no cover - local fallback when dependency is absent
    create_client = None


@deconstructible
class SupabaseStorage(Storage):
    def __init__(self):
        self.local_storage = FileSystemStorage(location=settings.MEDIA_ROOT, base_url=settings.MEDIA_URL)

    @property
    def enabled(self):
        return bool(
            create_client
            and settings.SUPABASE_URL
            and settings.SUPABASE_STORAGE_KEY
            and settings.SUPABASE_STORAGE_BUCKET
        )

    def _client(self):
        return create_client(settings.SUPABASE_URL, settings.SUPABASE_STORAGE_KEY)

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

    def _save(self, name, content):
        if not self.enabled:
            return self.local_storage._save(name, content)

        clean_name = self._clean_name(name)
        content.open("rb")
        payload = content.read()
        content_type = getattr(content, "content_type", None) or mimetypes.guess_type(clean_name)[0] or "application/octet-stream"

        self._client().storage.from_(settings.SUPABASE_STORAGE_BUCKET).upload(
            path=clean_name,
            file=payload,
            file_options={
                "content-type": content_type,
                "upsert": "false",
            },
        )
        return clean_name

    def delete(self, name):
        if not name:
            return

        if not self.enabled:
            self.local_storage.delete(name)
            return

        self._client().storage.from_(settings.SUPABASE_STORAGE_BUCKET).remove([self._clean_name(name)])

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
