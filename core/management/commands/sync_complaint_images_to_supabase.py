from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand

from core.models import Complaint


class Command(BaseCommand):
    help = "Upload existing complaint images from local MEDIA_ROOT to the configured default storage."

    def handle(self, *args, **options):
        uploaded = 0
        missing = 0
        skipped = 0

        for complaint in Complaint.objects.exclude(photo="").iterator():
            name = complaint.photo.name
            local_path = Path(settings.MEDIA_ROOT) / name

            if not local_path.exists():
                missing += 1
                self.stdout.write(self.style.WARNING(f"Missing local file for complaint {complaint.pk}: {name}"))
                continue

            with local_path.open("rb") as fh:
                try:
                    complaint.photo.storage._save(name, File(fh))
                except Exception as exc:
                    skipped += 1
                    self.stdout.write(
                        self.style.WARNING(f"Skipped complaint {complaint.pk}: {name} ({exc})")
                    )
                    continue

            uploaded += 1
            self.stdout.write(self.style.SUCCESS(f"Uploaded complaint {complaint.pk}: {name}"))

        self.stdout.write(
            self.style.SUCCESS(
                f"Completed. uploaded={uploaded} skipped={skipped} missing={missing}"
            )
        )
