"""
Vet Report AI Summarizer model.

VetReport — uploaded PDF/TXT vet document with Gemini-generated plain-English summary.
"""
from django.conf import settings
from django.db import models
from apps.cattle.models import Cattle


class VetReport(models.Model):

    class Status(models.TextChoices):
        PENDING = "pending_summarization", "Pending Summarization"
        READY = "summary_ready", "Summary Ready"
        FAILED = "summary_failed", "Summary Failed"

    cattle = models.ForeignKey(
        Cattle, on_delete=models.CASCADE, related_name="vet_reports"
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="uploaded_vet_reports",
    )
    upload_date = models.DateTimeField(auto_now_add=True)
    original_filename = models.CharField(max_length=255)
    file_path = models.FileField(upload_to="vet_reports/%Y/%m/")
    raw_text = models.TextField(blank=True, default="")
    ai_summary = models.TextField(blank=True, null=True)
    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.PENDING,
    )
    error_reason = models.TextField(blank=True, null=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "vet_reports"
        ordering = ["-upload_date"]
        verbose_name = "Vet Report"
        verbose_name_plural = "Vet Reports"

    def __str__(self):
        return f"VetReport [{self.status}] {self.cattle.tag_number} — {self.original_filename}"
