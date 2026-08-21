"""
vetreport.ai.summarizer
~~~~~~~~~~~~~~~~~~~~~~~

VetReportSummarizer
-------------------
Wraps the Google Gemini 1.5 Flash API to convert raw veterinary report text
into a plain-English farmer-facing summary.

Typical usage
~~~~~~~~~~~~~
    from apps.vetreport.ai import VetReportSummarizer

    summarizer = VetReportSummarizer()
    summary = summarizer.summarize(raw_text="...", cattle_name="Bessie")

Design notes
~~~~~~~~~~~~
* The Gemini client is initialised once at __init__ time.  The class is
  intentionally stateless beyond the client — safe to instantiate per-request
  or reuse as a module-level singleton.
* The prompt is structured to elicit a concise farmer-friendly response
  regardless of the verbosity of the original report.
* All API / network errors are caught and return the fallback string so the
  caller always receives a usable string (never raises).
* ``GEMINI_API_KEY`` is read from ``django.conf.settings`` (which in turn reads
  from the ``.env`` file via python-decouple).  A missing key triggers a
  descriptive ``ImproperlyConfigured`` error at init time rather than silently
  failing at summarisation time.
"""
from __future__ import annotations

import logging
import textwrap

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)

# Gemini model to use — 1.5-flash is fast and cost-effective for summarisation
GEMINI_MODEL = "gemini-1.5-flash"

# Fallback string returned on any API or parsing failure
FALLBACK_SUMMARY = (
    "Summary unavailable. Please review the original report."
)

# Prompt template — kept here so it's easy to A/B test or override
PROMPT_TEMPLATE = textwrap.dedent("""\
    You are a veterinary assistant helping a dairy farmer understand a vet report.

    Summarize the following veterinary report for the farmer who owns a dairy cow \
named "{cattle_name}". Write in plain, simple English that a non-medical person \
can understand. Structure your response with these four sections:

    1. **Diagnosis** – What is wrong with the cow?
    2. **Medications** – What medicines or treatments have been prescribed?
    3. **Follow-up Actions** – What does the farmer need to do next?
    4. **Warning Signs** – What symptoms should prompt an urgent vet call?

    Keep the entire summary under 200 words. Do not use medical jargon.

    Vet Report:
    {raw_text}
""")


class VetReportSummarizer:
    """
    Sends a structured prompt to Gemini 1.5 Flash and returns a plain-English
    summary of the veterinary report.

    Parameters
    ----------
    (none — API key and model are read from Django settings)

    Raises
    ------
    django.core.exceptions.ImproperlyConfigured
        If ``settings.GEMINI_API_KEY`` is empty or not set.
    """

    def __init__(self) -> None:
        api_key = getattr(settings, "GEMINI_API_KEY", "").strip()
        if not api_key:
            raise ImproperlyConfigured(
                "GEMINI_API_KEY is not configured. "
                "Add it to your .env file: GEMINI_API_KEY=your-key-here"
            )

        import google.generativeai as genai  # deferred — avoids slow startup

        genai.configure(api_key=api_key)
        self._client = genai.GenerativeModel(GEMINI_MODEL)
        logger.debug("VetReportSummarizer initialised with model=%s", GEMINI_MODEL)

    # ── Public API ────────────────────────────────────────────────────────────

    def summarize(self, raw_text: str, cattle_name: str) -> str:
        """
        Summarise *raw_text* for the farmer who owns *cattle_name*.

        Parameters
        ----------
        raw_text     : str — extracted text from the uploaded PDF or TXT file.
        cattle_name  : str — the cattle's name, used to personalise the prompt.

        Returns
        -------
        str
            A plain-English summary structured into four sections
            (Diagnosis, Medications, Follow-up Actions, Warning Signs), or
            the ``FALLBACK_SUMMARY`` constant if the API call fails.
        """
        if not raw_text or not raw_text.strip():
            logger.warning(
                "VetReportSummarizer.summarize() called with empty raw_text "
                "for cattle '%s'", cattle_name,
            )
            return FALLBACK_SUMMARY

        prompt = PROMPT_TEMPLATE.format(
            cattle_name=cattle_name.strip() or "the cow",
            raw_text=raw_text.strip(),
        )

        try:
            logger.info(
                "Sending vet report to Gemini (cattle='%s', text_len=%d)",
                cattle_name, len(raw_text),
            )
            response = self._client.generate_content(prompt)
            summary  = response.text.strip()

            if not summary:
                logger.warning(
                    "Gemini returned an empty response for cattle='%s'", cattle_name
                )
                return FALLBACK_SUMMARY

            logger.info(
                "Gemini summarisation complete for cattle='%s' (%d chars)",
                cattle_name, len(summary),
            )
            return summary

        except Exception as exc:  # noqa: BLE001 — intentional catch-all
            logger.error(
                "Gemini API error for cattle='%s': %s",
                cattle_name, exc, exc_info=True,
            )
            return FALLBACK_SUMMARY
