"""
vetreport/ai/summarizer.py
~~~~~~~~~~~~~~~~~~~~~~~~~~

VetReportSummarizer — calls Google Gemini 1.5 Flash to produce a
plain-English summary of a veterinary report.

Usage
-----
    from apps.vetreport.ai import VetReportSummarizer

    summarizer = VetReportSummarizer()
    summary = summarizer.summarize(raw_text="...", cattle_name="Bessie")
"""
import logging
import textwrap

from decouple import config
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)

GEMINI_MODEL  = "gemini-3.6-flash"
FALLBACK_TEXT = "Summary unavailable. Please review the original report."

PROMPT_TEMPLATE = textwrap.dedent("""\
    You are a veterinary assistant. Summarize this vet report for dairy farmer {cattle_name}
    in plain English. Highlight: diagnosis, medications, follow-up actions, and warning signs.
    Keep it under 200 words. Report: {raw_text}
""")


class VetReportSummarizer:
    """
    Sends structured prompts to Gemini 1.5 Flash and returns plain-English summaries.

    Raises
    ------
    ImproperlyConfigured   if GEMINI_API_KEY is empty or not set.
    """

    def __init__(self) -> None:
        api_key = config("GEMINI_API_KEY", default="").strip()
        if not api_key:
            raise ImproperlyConfigured(
                "GEMINI_API_KEY is not configured. "
                "Add it to your .env file: GEMINI_API_KEY=your-key-here"
            )

        import google.generativeai as genai  # deferred import
        genai.configure(api_key=api_key)
        self._client = genai.GenerativeModel(GEMINI_MODEL)
        logger.debug("VetReportSummarizer initialised (model=%s)", GEMINI_MODEL)

    def summarize(self, raw_text: str, cattle_name: str) -> str:
        """
        Summarise *raw_text* for the farmer who owns *cattle_name*.

        Returns the AI-generated summary string, or FALLBACK_TEXT on any error.
        Never raises.
        """
        if not raw_text or not raw_text.strip():
            logger.warning("VetReportSummarizer.summarize: empty raw_text for '%s'", cattle_name)
            return FALLBACK_TEXT

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
                return FALLBACK_TEXT
            logger.info("Gemini summary complete (%d chars)", len(summary))
            return summary
        except Exception as exc:
            logger.error("Gemini API error for cattle='%s': %s", cattle_name, exc, exc_info=True)
            return FALLBACK_TEXT
