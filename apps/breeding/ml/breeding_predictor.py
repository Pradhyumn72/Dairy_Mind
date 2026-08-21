"""
Breeding ML Predictor
=====================

BreedingPredictor
-----------------
Two core methods:

predict_best_breeding_window(cattle_id)
    Uses historical HeatCycleLog entries to compute the average inter-heat
    interval and project the next heat + optimal insemination window.

predict_ai_success_probability(cattle_id)
    Uses historical ArtificialInsemination outcomes to train a
    scikit-learn LogisticRegression (MODEL path) or falls back to a
    calibrated heuristic when fewer than 5 completed AI records exist
    (HEURISTIC path).
"""
import logging
from datetime import date, timedelta, datetime
from typing import Any

logger = logging.getLogger(__name__)


class BreedingPredictor:
    """
    ML-backed predictor for cattle breeding decisions.

    All DB queries are lazy (executed only when the method is called) so
    the class is cheap to instantiate.
    """

    # ── Internal constants ────────────────────────────────────────────────────

    _INTENSITY_SCORE = {
        "WEAK": 0,
        "MODERATE": 1,
        "STRONG": 2,
    }

    # Minimum number of *completed* (non-PENDING) AI records required to
    # train the logistic regression model.
    _MIN_MODEL_SAMPLES = 5

    # ─────────────────────────────────────────────────────────────────────────
    # Method 1 — predict_best_breeding_window
    # ─────────────────────────────────────────────────────────────────────────

    def predict_best_breeding_window(self, cattle_id: int) -> dict[str, Any]:
        """
        Predict the next heat window and optimal AI date for a cattle.

        Parameters
        ----------
        cattle_id : int
            Primary key of the Cattle record.

        Returns
        -------
        dict
            On success::

                {
                    "predicted_next_heat":   "YYYY-MM-DD",
                    "best_ai_date":          "YYYY-MM-DD",
                    "optimal_window_start":  "YYYY-MM-DDTHH:MM",
                    "optimal_window_end":    "YYYY-MM-DDTHH:MM",
                    "avg_cycle_length_days": float,
                    "cycles_analyzed":       int,
                    "confidence":            "LOW" | "MEDIUM" | "HIGH",
                }

            On insufficient data::

                {"error": "insufficient_data", "cycles_found": N}

        Notes
        -----
        * Requires at least 2 HeatCycleLog entries.
        * Confidence levels:
            - LOW    : 2 cycles analyzed (intervals == 1)
            - MEDIUM : 3–5 cycles analyzed (intervals 2–4)
            - HIGH   : > 5 cycles analyzed (intervals >= 5)
        """
        from apps.breeding.models import HeatCycleLog  # local import avoids circular

        logs = list(
            HeatCycleLog.objects
            .filter(cattle_id=cattle_id)
            .order_by("observed_date")
            .values_list("observed_date", flat=True)
        )

        n = len(logs)

        if n < 2:
            return {"error": "insufficient_data", "cycles_found": n}

        # ── Calculate average inter-heat interval ─────────────────────────────
        intervals = [
            (logs[i] - logs[i - 1]).days
            for i in range(1, n)
        ]
        avg_interval = sum(intervals) / len(intervals)

        last_heat: date = logs[-1]
        predicted_heat_start: date = last_heat + timedelta(days=round(avg_interval))

        # Optimal insemination window: +12 h to +18 h, best at +15 h
        base_dt      = datetime.combine(predicted_heat_start, datetime.min.time())
        window_start = base_dt + timedelta(hours=12)
        window_end   = base_dt + timedelta(hours=18)
        best_ai_dt   = base_dt + timedelta(hours=15)

        # Confidence: based on number of inter-heat intervals used
        cycles_analyzed = n - 1
        if cycles_analyzed < 3:
            confidence = "LOW"
        elif cycles_analyzed <= 5:
            confidence = "MEDIUM"
        else:
            confidence = "HIGH"

        return {
            "predicted_next_heat":  predicted_heat_start.strftime("%Y-%m-%d"),
            "best_ai_date":         best_ai_dt.strftime("%Y-%m-%d"),
            "optimal_window_start": window_start.strftime("%Y-%m-%dT%H:%M"),
            "optimal_window_end":   window_end.strftime("%Y-%m-%dT%H:%M"),
            "avg_cycle_length_days": round(avg_interval, 2),
            "cycles_analyzed":       cycles_analyzed,
            "confidence":            confidence,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Method 2 — predict_ai_success_probability
    # ─────────────────────────────────────────────────────────────────────────

    def predict_ai_success_probability(self, cattle_id: int) -> dict[str, Any]:
        """
        Estimate the probability of a successful AI outcome.

        Parameters
        ----------
        cattle_id : int
            Primary key of the Cattle record.

        Returns
        -------
        dict
            {
                "success_probability": float (0.0–1.0),
                "success_percent":     int,
                "confidence":          "HEURISTIC" | "MODEL",
                "key_factors":         [str, ...],
                "recommendation":      str,
            }

        Logic
        -----
        If ≥ 5 historical AI records with known outcomes exist across the
        *whole farm*, a LogisticRegression model is trained on those records
        and used to predict for this cattle's current features.

        Otherwise a calibrated heuristic is applied:
            base  = 0.55
            +0.10 if last heat intensity == STRONG
            -0.08 if cattle age > 8 years
            -0.05 if days_since_last_calving < 60
        """
        from apps.cattle.models import Cattle
        from apps.breeding.models import (
            ArtificialInsemination,
            HeatCycleLog,
            PregnancyRecord,
        )

        # ── Resolve cattle record ─────────────────────────────────────────────
        try:
            cattle = Cattle.objects.get(pk=cattle_id)
        except Cattle.DoesNotExist:
            return {"error": "cattle_not_found", "cattle_id": cattle_id}

        today = date.today()

        # ── Feature extraction for *this* cattle ─────────────────────────────

        # age_at_ai (years)
        age_years = (today - cattle.date_of_birth).days / 365.25

        # days_since_last_calving
        last_pregnancy = (
            PregnancyRecord.objects
            .filter(cattle_id=cattle_id, actual_calving_date__isnull=False)
            .order_by("-actual_calving_date")
            .first()
        )
        days_since_calving = (
            (today - last_pregnancy.actual_calving_date).days
            if last_pregnancy
            else 0
        )

        # heat_intensity of the most recent HeatCycleLog
        latest_heat = (
            HeatCycleLog.objects
            .filter(cattle_id=cattle_id)
            .order_by("-observed_date")
            .first()
        )
        heat_intensity_str   = latest_heat.intensity if latest_heat else "MODERATE"
        heat_intensity_score = self._INTENSITY_SCORE.get(heat_intensity_str, 1)

        # ai_attempt_number — how many AIs has this cattle had previously
        ai_attempt_number = ArtificialInsemination.objects.filter(
            cattle_id=cattle_id
        ).count()

        # ── Farm-level historical AI records (completed outcomes only) ────────
        completed_ais = list(
            ArtificialInsemination.objects
            .exclude(outcome=ArtificialInsemination.Outcome.PENDING)
            .select_related("cattle")
            .order_by("ai_date")
        )

        use_model = len(completed_ais) >= self._MIN_MODEL_SAMPLES

        if use_model:
            return self._predict_via_model(
                completed_ais=completed_ais,
                age_years=age_years,
                days_since_calving=days_since_calving,
                heat_intensity_score=heat_intensity_score,
                ai_attempt_number=ai_attempt_number,
                heat_intensity_str=heat_intensity_str,
                today=today,
            )
        return self._predict_via_heuristic(
            age_years=age_years,
            days_since_calving=days_since_calving,
            heat_intensity_str=heat_intensity_str,
            heat_intensity_score=heat_intensity_score,
            ai_attempt_number=ai_attempt_number,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Private helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _build_feature_row(self, ai, today: date) -> list[float]:
        """
        Build a single feature vector for one ArtificialInsemination record.

        Features (in order):
          0: age_at_ai          — years at time of AI
          1: days_since_calving — 0 if first calving / no prior pregnancy
          2: heat_intensity     — WEAK=0 / MODERATE=1 / STRONG=2
          3: ai_attempt_number  — count of AIs *before* this one for this cattle
        """
        from apps.breeding.models import ArtificialInsemination, HeatCycleLog, PregnancyRecord

        ai_date = ai.ai_date

        # Age at AI date
        age_at_ai = (ai_date - ai.cattle.date_of_birth).days / 365.25

        # Days since last calving prior to AI date
        prev_calving = (
            PregnancyRecord.objects
            .filter(
                cattle=ai.cattle,
                actual_calving_date__lt=ai_date,
            )
            .order_by("-actual_calving_date")
            .first()
        )
        days_since_calving = (
            (ai_date - prev_calving.actual_calving_date).days
            if prev_calving
            else 0
        )

        # Heat intensity nearest to and before AI date
        nearest_heat = (
            HeatCycleLog.objects
            .filter(
                cattle=ai.cattle,
                observed_date__lte=ai_date,
            )
            .order_by("-observed_date")
            .first()
        )
        intensity_score = self._INTENSITY_SCORE.get(
            nearest_heat.intensity if nearest_heat else "MODERATE", 1
        )

        # Number of AIs before this one for the same cattle
        prior_ais = (
            ArtificialInsemination.objects
            .filter(cattle=ai.cattle, ai_date__lt=ai_date)
            .count()
        )

        return [age_at_ai, float(days_since_calving), float(intensity_score), float(prior_ais)]

    def _predict_via_model(
        self,
        completed_ais: list,
        age_years: float,
        days_since_calving: int,
        heat_intensity_score: int,
        ai_attempt_number: int,
        heat_intensity_str: str,
        today: date,
    ) -> dict[str, Any]:
        """Train a LogisticRegression on farm history and predict."""
        try:
            from sklearn.linear_model import LogisticRegression
            from sklearn.preprocessing import StandardScaler
            import numpy as np
            from apps.breeding.models import ArtificialInsemination
        except ImportError as exc:
            logger.warning(
                "scikit-learn not available, falling back to heuristic: %s", exc
            )
            return self._predict_via_heuristic(
                age_years=age_years,
                days_since_calving=days_since_calving,
                heat_intensity_str=heat_intensity_str,
                heat_intensity_score=heat_intensity_score,
                ai_attempt_number=ai_attempt_number,
            )

        X_rows, y_labels = [], []
        for ai in completed_ais:
            try:
                row   = self._build_feature_row(ai, today)
                label = 1 if ai.outcome == ArtificialInsemination.Outcome.CONFIRMED_PREGNANT else 0
                X_rows.append(row)
                y_labels.append(label)
            except Exception as exc:
                logger.debug(
                    "Skipping AI record %s during feature extraction: %s", ai.pk, exc
                )
                continue

        if len(X_rows) < self._MIN_MODEL_SAMPLES:
            # Insufficient usable rows after filtering — fall back to heuristic
            return self._predict_via_heuristic(
                age_years=age_years,
                days_since_calving=days_since_calving,
                heat_intensity_str=heat_intensity_str,
                heat_intensity_score=heat_intensity_score,
                ai_attempt_number=ai_attempt_number,
            )

        X = np.array(X_rows)
        y = np.array(y_labels)
        X_scaled = scaler.fit_transform(X)

        model = LogisticRegression(max_iter=200, random_state=42)
        model.fit(X_scaled, y)

        X_pred = scaler.transform(
            [[age_years, float(days_since_calving), float(heat_intensity_score), float(ai_attempt_number)]]
        )
        prob = float(model.predict_proba(X_pred)[0][1])
        prob = max(0.0, min(1.0, prob))

        # Key factors derived from model coefficients
        feature_names  = ["age_at_ai", "days_since_calving", "heat_intensity", "ai_attempt_number"]
        coefficients   = model.coef_[0]
        sorted_factors = sorted(
            zip(feature_names, coefficients),
            key=lambda t: abs(t[1]),
            reverse=True,
        )
        key_factors = [
            _coef_to_explanation(name, coef)
            for name, coef in sorted_factors[:3]
        ]

        recommendation = _build_recommendation(
            prob, heat_intensity_str, days_since_calving, age_years
        )

        return {
            "success_probability": round(prob, 4),
            "success_percent":     int(round(prob * 100)),
            "confidence":          "MODEL",
            "key_factors":         key_factors,
            "recommendation":      recommendation,
        }

    def _predict_via_heuristic(
        self,
        age_years: float,
        days_since_calving: int,
        heat_intensity_str: str,
        heat_intensity_score: int,
        ai_attempt_number: int,
    ) -> dict[str, Any]:
        """Calibrated heuristic for cold-start cases (< 5 historical AIs)."""
        prob    = 0.55
        factors = []

        # Heat intensity
        if heat_intensity_str == "STRONG":
            prob += 0.10
            factors.append("Strong heat intensity detected — increases success likelihood")
        elif heat_intensity_str == "WEAK":
            factors.append("Weak heat intensity — sub-optimal insemination timing possible")
        else:
            factors.append("Moderate heat intensity observed")

        # Age penalty
        if age_years > 8:
            prob -= 0.08
            factors.append(
                f"Cattle age ({age_years:.1f} yrs) exceeds 8 years — fertility may be reduced"
            )
        else:
            factors.append(
                f"Cattle age ({age_years:.1f} yrs) is within the normal fertile range"
            )

        # Postpartum recovery penalty
        if 0 < days_since_calving < 60:
            prob -= 0.05
            factors.append(
                f"Only {days_since_calving} days since last calving — "
                "postpartum recovery may affect conception rate"
            )
        elif days_since_calving == 0:
            factors.append("No prior calving records — treating as first-time breeding")
        else:
            factors.append(
                f"Days since last calving ({days_since_calving}) is adequate for breeding"
            )

        prob = max(0.0, min(1.0, prob))

        return {
            "success_probability": round(prob, 4),
            "success_percent":     int(round(prob * 100)),
            "confidence":          "HEURISTIC",
            "key_factors":         factors,
            "recommendation":      _build_recommendation(
                prob, heat_intensity_str, days_since_calving, age_years
            ),
        }


# ── Module-level helpers ──────────────────────────────────────────────────────

def _coef_to_explanation(feature: str, coef: float) -> str:
    """Convert a logistic regression coefficient into a human-readable string."""
    direction = "increases" if coef > 0 else "decreases"
    labels = {
        "age_at_ai":          "Cattle age",
        "days_since_calving": "Days since last calving",
        "heat_intensity":     "Heat intensity",
        "ai_attempt_number":  "Number of prior AI attempts",
    }
    return (
        f"{labels.get(feature, feature)} {direction} success probability "
        f"(coef={coef:+.3f})"
    )


def _build_recommendation(
    prob: float,
    heat_intensity_str: str,
    days_since_calving: int,
    age_years: float,
) -> str:
    """Compose a plain-English recommendation string."""
    if prob >= 0.70:
        action = "Proceed with AI — conditions appear favourable."
    elif prob >= 0.50:
        action = (
            "AI can be attempted; monitor post-AI for any signs of return to heat."
        )
    else:
        action = (
            "Consider postponing AI until contributing risk factors improve "
            "(e.g., allow more post-calving recovery time or wait for stronger heat signs)."
        )

    notes = []
    if heat_intensity_str == "WEAK":
        notes.append(
            "Heat signs are weak — confirm standing heat before proceeding."
        )
    if 0 < days_since_calving < 45:
        notes.append(
            "Animal is in early postpartum period; "
            "allow at least 45 days before AI if possible."
        )
    if age_years > 10:
        notes.append(
            "Animal is older than 10 years; "
            "consult a vet for a reproductive health assessment."
        )

    if notes:
        return f"{action} Additional notes: {' '.join(notes)}"
    return action
