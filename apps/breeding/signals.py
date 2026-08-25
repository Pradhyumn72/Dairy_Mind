"""
breeding/signals.py
~~~~~~~~~~~~~~~~~~~~

Cross-module health alert generation from breeding sign observations.

When a HeatCycleLog is created or updated two independent checks run:

1. LITERAL SYMPTOM SCAN
   The ``signs`` text field is scanned for illness-indicating keywords that
   are NOT consistent with a normal heat event (e.g. fever, lethargy,
   diarrhea).  If any match is found, a HealthAlert of type MANUAL /
   severity MEDIUM is created.

2. MILK ANOMALY CROSS-DETECTION
   The cattle's last 14 days of MilkLog total_litres are fetched.  If at
   least 7 days of data exist, MilkAnomalyDetector is fitted on all-but-the-
   most-recent value, then predict() is called on the most-recent day's
   total_litres.  If an anomaly is detected, a HealthAlert of type ANOMALY
   is created (severity from the detector result), unless an unresolved
   ANOMALY alert already exists for this cattle on the same day.

The signal receiver is connected inside BreedingConfig.ready() via:

    from apps.breeding import signals  # noqa: F401

This file only defines the keyword list, the matching helper, the anomaly
helper, and the single receiver.  Nothing is imported at module load time —
all Django-model/ML imports are deferred to keep the receiver safe during
Django's startup sequence.
"""
import logging
import re

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)

# ── Illness keyword list ──────────────────────────────────────────────────────
# Words/phrases that suggest illness rather than a normal heat/estrus event.
# All comparisons are case-insensitive; partial matches within words are fine
# (e.g. "feverish" matches "fever").

ILLNESS_KEYWORDS: list[str] = [
    "fever",
    "stomach pain",
    "diarrhea",
    "diarrhoea",
    "lethargy",
    "lethargic",
    "not eating",
    "off feed",
    "swelling",
    "swollen",
    "discharge",
    "nasal discharge",
    "coughing",
    "cough",
    "limping",
    "lame",
    "lameness",
    "shivering",
    "trembling",
    "bloat",
    "bloating",
    "laboured breathing",
    "labored breathing",
    "grinding teeth",
    "weight loss",
    "pale gums",
    "sunken eyes",
    "runny nose",
    "abscess",
    "wound",
    "injury",
    "vomiting",
]

# Pre-compile patterns once at import time for speed.
# Each keyword is matched as a standalone phrase (word-boundary aware where
# the phrase starts/ends with a word character).
_PATTERNS: list[tuple[str, re.Pattern]] = [
    (kw, re.compile(r"(?<!\w)" + re.escape(kw) + r"(?!\w)", re.IGNORECASE))
    for kw in ILLNESS_KEYWORDS
]


def find_illness_keywords(signs_text: str) -> list[str]:
    """
    Return all illness keywords found in *signs_text*.

    Parameters
    ----------
    signs_text : str — the free-text ``signs`` field from a HeatCycleLog

    Returns
    -------
    list[str] — matched keywords, in the order they appear in ILLNESS_KEYWORDS.
                Empty list if no matches.
    """
    if not signs_text or not signs_text.strip():
        return []
    return [kw for kw, pattern in _PATTERNS if pattern.search(signs_text)]


# ── Milk anomaly cross-detection helper ───────────────────────────────────────

def _run_milk_anomaly_check(instance) -> None:
    """
    Fetch the last 14 days of MilkLog for *instance.cattle*, fit
    MilkAnomalyDetector on all-but-the-last value, and predict on the last.
    Creates a HealthAlert(ANOMALY) if an anomaly is detected and no
    unresolved ANOMALY alert already exists for the same cattle+date.

    Silently skips if fewer than 7 days of milk history are available.
    All exceptions are caught and logged so they never break the save path.
    """
    try:
        from datetime import date, timedelta

        # Deferred imports — safe during Django startup
        from apps.milk.models import MilkLog
        from apps.health.ml.anomaly_detector import MilkAnomalyDetector
        from apps.health.models import HealthAlert

        cattle      = instance.cattle
        cutoff      = instance.observed_date - timedelta(days=14)

        # Ordered oldest → newest so the last element is the most recent day
        milk_values = list(
            MilkLog.objects
            .filter(cattle=cattle, date__gte=cutoff)
            .order_by("date")
            .values_list("total_litres", flat=True)
        )

        if len(milk_values) < 7:
            logger.debug(
                "[breeding.signals] Skipping anomaly check for cattle=%s: "
                "only %d days of milk history (need 7)",
                cattle.tag_number, len(milk_values),
            )
            return

        # Split: all-but-last for training, last for prediction
        train_values  = [float(v) for v in milk_values[:-1]]
        latest_value  = float(milk_values[-1])

        # Need at least MIN_HISTORY (7) points to fit — train_values has len-1
        if len(train_values) < 7:
            logger.debug(
                "[breeding.signals] Skipping anomaly check for cattle=%s: "
                "only %d training points after reserving latest",
                cattle.tag_number, len(train_values),
            )
            return

        detector = MilkAnomalyDetector()
        detector.fit(train_values)
        result = detector.predict(latest_value)

        if not result.get("is_anomaly"):
            logger.debug(
                "[breeding.signals] No milk anomaly for cattle=%s (score=%s)",
                cattle.tag_number, result.get("anomaly_score"),
            )
            return

        # Duplicate guard — skip if an unresolved ANOMALY alert already
        # exists for this cattle on the same observed_date
        already_exists = HealthAlert.objects.filter(
            cattle      = cattle,
            alert_date  = instance.observed_date,
            alert_type  = HealthAlert.AlertType.ANOMALY,
            is_resolved = False,
        ).exists()

        if already_exists:
            logger.info(
                "[breeding.signals] Skipping duplicate ANOMALY alert for "
                "cattle=%s on %s",
                cattle.tag_number, instance.observed_date,
            )
            return

        message = (
            f"Milk production anomaly detected near breeding log entry "
            f"on {instance.observed_date}: {result['message']}"
        )

        HealthAlert.objects.create(
            cattle      = cattle,
            alert_date  = instance.observed_date,
            alert_type  = HealthAlert.AlertType.ANOMALY,
            severity    = result["severity"],
            message     = message,
            is_resolved = False,
        )

        logger.warning(
            "[breeding.signals] ANOMALY HealthAlert created for cattle=%s "
            "on %s — severity=%s score=%s",
            cattle.tag_number, instance.observed_date,
            result["severity"], result.get("anomaly_score"),
        )

    except Exception as exc:
        # Never let the anomaly check crash the HeatCycleLog save
        logger.error(
            "[breeding.signals] Unexpected error in milk anomaly check "
            "for cattle=%s: %s",
            getattr(getattr(instance, "cattle", None), "tag_number", "?"),
            exc,
            exc_info=True,
        )


# ── Signal receiver ───────────────────────────────────────────────────────────

@receiver(post_save, sender="breeding.HeatCycleLog")
def check_illness_signs_in_heat_log(sender, instance, created, **kwargs):
    """
    After a HeatCycleLog is saved (created OR updated), run two independent
    health checks:

    1. Literal keyword scan on ``signs`` → MANUAL HealthAlert on match.
    2. Milk anomaly cross-detection     → ANOMALY HealthAlert on detection.
    """
    # ── Check 1: literal symptom keywords (unchanged) ────────────────────────
    signs_text = instance.signs or ""
    matched    = find_illness_keywords(signs_text)

    if matched:
        matched_display = ", ".join(f"'{kw}'" for kw in matched)
        message = (
            f"Non-heat symptoms detected in breeding log: {matched_display}. "
            "Recommend health check."
        )

        logger.warning(
            "[breeding.signals] Illness keywords %s found in HeatCycleLog id=%d "
            "for cattle=%s — creating HealthAlert",
            matched, instance.pk, instance.cattle.tag_number,
        )

        # Deferred imports keep this safe during Django startup
        from apps.health.models import HealthAlert

        HealthAlert.objects.create(
            cattle      = instance.cattle,
            alert_date  = instance.observed_date,
            alert_type  = HealthAlert.AlertType.MANUAL,
            severity    = HealthAlert.Severity.MEDIUM,
            message     = message,
            is_resolved = False,
        )

        logger.info(
            "[breeding.signals] HealthAlert created for cattle=%s (keywords: %s)",
            instance.cattle.tag_number, matched,
        )

    # ── Check 2: milk anomaly cross-detection ─────────────────────────────────
    _run_milk_anomaly_check(instance)

import logging
import re

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)

# ── Illness keyword list ──────────────────────────────────────────────────────
# Words/phrases that suggest illness rather than a normal heat/estrus event.
# All comparisons are case-insensitive; partial matches within words are fine
# (e.g. "feverish" matches "fever").

ILLNESS_KEYWORDS: list[str] = [
    "fever",
    "stomach pain",
    "diarrhea",
    "diarrhoea",
    "lethargy",
    "lethargic",
    "not eating",
    "off feed",
    "swelling",
    "swollen",
    "discharge",
    "nasal discharge",
    "coughing",
    "cough",
    "limping",
    "lame",
    "lameness",
    "shivering",
    "trembling",
    "bloat",
    "bloating",
    "laboured breathing",
    "labored breathing",
    "grinding teeth",
    "weight loss",
    "pale gums",
    "sunken eyes",
    "runny nose",
    "abscess",
    "wound",
    "injury",
    "vomiting",
]

# Pre-compile patterns once at import time for speed.
# Each keyword is matched as a standalone phrase (word-boundary aware where
# the phrase starts/ends with a word character).
_PATTERNS: list[tuple[str, re.Pattern]] = [
    (kw, re.compile(r"(?<!\w)" + re.escape(kw) + r"(?!\w)", re.IGNORECASE))
    for kw in ILLNESS_KEYWORDS
]


def find_illness_keywords(signs_text: str) -> list[str]:
    """
    Return all illness keywords found in *signs_text*.

    Parameters
    ----------
    signs_text : str — the free-text ``signs`` field from a HeatCycleLog

    Returns
    -------
    list[str] — matched keywords, in the order they appear in ILLNESS_KEYWORDS.
                Empty list if no matches.
    """
    if not signs_text or not signs_text.strip():
        return []
    return [kw for kw, pattern in _PATTERNS if pattern.search(signs_text)]


# ── Signal receiver ───────────────────────────────────────────────────────────

@receiver(post_save, sender="breeding.HeatCycleLog")
def check_illness_signs_in_heat_log(sender, instance, created, **kwargs):
    """
    After a HeatCycleLog is saved (created OR updated), scan ``signs`` for
    illness keywords.  If any are found, create a HealthAlert for the cattle.

    A new alert is created on every save where illness keywords are present —
    this means updates that add new symptoms also trigger fresh alerts, which
    is intentional (the farmer should be notified again if signs worsen).
    """
    signs_text = instance.signs or ""
    matched    = find_illness_keywords(signs_text)

    if not matched:
        return  # normal heat signs only — nothing to do

    matched_display = ", ".join(f"'{kw}'" for kw in matched)
    message = (
        f"Non-heat symptoms detected in breeding log: {matched_display}. "
        "Recommend health check."
    )

    logger.warning(
        "[breeding.signals] Illness keywords %s found in HeatCycleLog id=%d "
        "for cattle=%s — creating HealthAlert",
        matched, instance.pk, instance.cattle.tag_number,
    )

    # Deferred imports keep this safe during Django startup
    from django.utils import timezone
    from apps.health.models import HealthAlert

    HealthAlert.objects.create(
        cattle      = instance.cattle,
        alert_date  = instance.observed_date,
        alert_type  = HealthAlert.AlertType.MANUAL,
        severity    = HealthAlert.Severity.MEDIUM,
        message     = message,
        is_resolved = False,
    )

    logger.info(
        "[breeding.signals] HealthAlert created for cattle=%s (keywords: %s)",
        instance.cattle.tag_number, matched,
    )
