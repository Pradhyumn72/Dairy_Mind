"""
Unit tests for BreedingPredictor.

Scenarios covered
-----------------
1. Cattle with 6 regular heat cycles  → HIGH confidence, full window prediction
2. Cattle with 1 heat cycle           → insufficient_data error path
3. Cold-start AI probability          → HEURISTIC confidence path

Patching strategy
-----------------
The predictor uses local (deferred) imports inside each method, so the
objects live at their canonical module paths:

    apps.breeding.models.HeatCycleLog
    apps.cattle.models.Cattle
    apps.breeding.models.ArtificialInsemination
    apps.breeding.models.PregnancyRecord

We patch at those paths rather than at the predictor module level.
"""
import pytest
from datetime import date, timedelta
from unittest.mock import MagicMock, patch


# ─────────────────────────────────────────────────────────────────────────────
# Helpers — build lightweight mock objects that mimic Django model instances
# ─────────────────────────────────────────────────────────────────────────────

def _make_cattle(pk: int = 1, dob: date = None) -> MagicMock:
    """Return a mock Cattle instance."""
    m = MagicMock()
    m.pk            = pk
    m.tag_number    = f"TAG-{pk:03d}"
    m.name          = f"Cattle {pk}"
    m.gender        = "Female"
    m.is_active     = True
    m.date_of_birth = dob or date(2016, 1, 1)
    return m


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 1 — 6 regular heat cycles (HIGH confidence)
# ─────────────────────────────────────────────────────────────────────────────

class TestPredictBestBreedingWindowHighConfidence:
    """
    Cattle ID 1 has 7 heat-log dates (6 intervals, all 21 days apart).
    Expected: HIGH confidence, avg_cycle_length_days == 21.0, cycles_analyzed == 6.
    """

    CATTLE_ID  = 1
    BASE_DATE  = date(2026, 1, 1)
    HEAT_DATES = [date(2026, 1, 1) + timedelta(days=21 * i) for i in range(7)]

    def _run(self):
        from apps.breeding.ml.breeding_predictor import BreedingPredictor

        dates_flat = self.HEAT_DATES

        mock_qs = MagicMock()
        mock_qs.filter.return_value.order_by.return_value.values_list.return_value = dates_flat

        with patch("apps.breeding.models.HeatCycleLog.objects", mock_qs):
            predictor = BreedingPredictor()
            # Directly call _predict_best_breeding_window_from_dates to bypass ORM
            # We simulate what the method does by building a fake HeatCycleLog class
            # that returns our dates.
            return predictor.predict_best_breeding_window(self.CATTLE_ID)

    def _run_direct(self):
        """
        Call the predictor by patching apps.breeding.models at the right place.
        This is the correct approach since the predictor uses local imports.
        """
        from apps.breeding.ml.breeding_predictor import BreedingPredictor

        dates_flat = self.HEAT_DATES

        with patch("apps.breeding.models.HeatCycleLog") as MockHL:
            mock_qs = MockHL.objects.filter.return_value.order_by.return_value
            mock_qs.values_list.return_value = dates_flat

            predictor = BreedingPredictor()
            return predictor.predict_best_breeding_window(self.CATTLE_ID)

    def test_no_error_key(self):
        result = self._run_direct()
        assert "error" not in result

    def test_confidence_is_high(self):
        result = self._run_direct()
        assert result["confidence"] == "HIGH"

    def test_cycles_analyzed(self):
        result = self._run_direct()
        assert result["cycles_analyzed"] == 6

    def test_avg_cycle_length(self):
        result = self._run_direct()
        assert result["avg_cycle_length_days"] == 21.0

    def test_predicted_heat_is_after_last(self):
        result = self._run_direct()
        predicted = date.fromisoformat(result["predicted_next_heat"])
        assert predicted > self.HEAT_DATES[-1]

    def test_window_start_before_end(self):
        result = self._run_direct()
        from datetime import datetime
        start = datetime.fromisoformat(result["optimal_window_start"])
        end   = datetime.fromisoformat(result["optimal_window_end"])
        assert start < end

    def test_window_span_is_6_hours(self):
        result = self._run_direct()
        from datetime import datetime
        start = datetime.fromisoformat(result["optimal_window_start"])
        end   = datetime.fromisoformat(result["optimal_window_end"])
        assert (end - start) == timedelta(hours=6)

    def test_best_ai_date_matches_predicted_heat_date(self):
        """best_ai_date should be the same calendar day as predicted_next_heat."""
        result = self._run_direct()
        assert result["best_ai_date"] == result["predicted_next_heat"]

    def test_required_keys_present(self):
        result = self._run_direct()
        required = {
            "predicted_next_heat",
            "best_ai_date",
            "optimal_window_start",
            "optimal_window_end",
            "avg_cycle_length_days",
            "cycles_analyzed",
            "confidence",
        }
        assert required.issubset(result.keys())


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 2 — Cattle with 1 heat cycle (insufficient data)
# ─────────────────────────────────────────────────────────────────────────────

class TestPredictBestBreedingWindowInsufficientData:
    """
    Cattle ID 2 has only 1 (or 0) heat-log entries.
    Expected: error == 'insufficient_data'.
    """

    CATTLE_ID = 2

    def _run(self, n_logs: int):
        from apps.breeding.ml.breeding_predictor import BreedingPredictor

        dates_flat = [date(2026, 5, 1) + timedelta(days=i) for i in range(n_logs)]

        with patch("apps.breeding.models.HeatCycleLog") as MockHL:
            mock_qs = MockHL.objects.filter.return_value.order_by.return_value
            mock_qs.values_list.return_value = dates_flat

            predictor = BreedingPredictor()
            return predictor.predict_best_breeding_window(self.CATTLE_ID)

    def test_error_key_is_insufficient_data(self):
        result = self._run(1)
        assert result.get("error") == "insufficient_data"

    def test_cycles_found_is_1(self):
        result = self._run(1)
        assert result.get("cycles_found") == 1

    def test_no_logs_returns_zero_cycles(self):
        result = self._run(0)
        assert result.get("error") == "insufficient_data"
        assert result.get("cycles_found") == 0

    def test_no_prediction_keys_present(self):
        result = self._run(1)
        assert "predicted_next_heat" not in result
        assert "best_ai_date" not in result


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 3 — Cold-start AI probability (heuristic path)
# ─────────────────────────────────────────────────────────────────────────────

class TestAISuccessProbabilityHeuristic:
    """
    Cold-start scenario: fewer than 5 completed AIs on the farm → heuristic path.

    Sub-scenarios:
      3a. STRONG heat, young cow, adequate recovery  → probability >= 0.65
      3b. WEAK heat, old cow (>8 yrs), recent calving (<60 days) → prob <= 0.45
      3c. No prior calving → days_since_calving == 0, no calving penalty
    """

    CATTLE_ID = 3

    def _run(
        self,
        dob: date,
        heat_intensity: str,
        last_calving_date=None,
    ):
        """
        Patch all ORM interactions and invoke predict_ai_success_probability.
        The farm-wide completed AI list is always empty → heuristic path.
        """
        from apps.breeding.ml.breeding_predictor import BreedingPredictor

        mock_cattle = _make_cattle(pk=self.CATTLE_ID, dob=dob)

        with patch("apps.cattle.models.Cattle") as MockCattle, \
             patch("apps.breeding.models.PregnancyRecord") as MockPR, \
             patch("apps.breeding.models.HeatCycleLog") as MockHL, \
             patch("apps.breeding.models.ArtificialInsemination") as MockAI:

            # Cattle.objects.get
            MockCattle.objects.get.return_value = mock_cattle

            # Last pregnancy (calving date)
            if last_calving_date:
                mock_preg = MagicMock()
                mock_preg.actual_calving_date = last_calving_date
                MockPR.objects.filter.return_value \
                    .order_by.return_value \
                    .first.return_value = mock_preg
            else:
                MockPR.objects.filter.return_value \
                    .order_by.return_value \
                    .first.return_value = None

            # Latest heat log
            mock_heat = MagicMock()
            mock_heat.intensity = heat_intensity
            MockHL.objects.filter.return_value \
                .order_by.return_value \
                .first.return_value = mock_heat

            # AI attempt count for this cattle
            MockAI.objects.filter.return_value.count.return_value = 1

            # Farm-level completed AIs → empty list forces heuristic
            MockAI.Outcome.PENDING = "PENDING"
            mock_exclude_qs = MagicMock()
            mock_exclude_qs.__len__ = lambda self: 0
            mock_exclude_qs.__iter__ = lambda self: iter([])
            MockAI.objects.exclude.return_value \
                .select_related.return_value \
                .order_by.return_value = []

            predictor = BreedingPredictor()
            return predictor.predict_ai_success_probability(self.CATTLE_ID)

    # ── 3a. STRONG heat, young cow, adequate recovery ─────────────────────────

    def test_3a_confidence_is_heuristic(self):
        result = self._run(
            dob=date(2020, 1, 1),
            heat_intensity="STRONG",
            last_calving_date=date(2025, 12, 1),  # ~262 days ago
        )
        assert result["confidence"] == "HEURISTIC"

    def test_3a_strong_heat_boosts_probability(self):
        """STRONG heat should yield prob >= 0.65 (base 0.55 + 0.10)."""
        result = self._run(
            dob=date(2020, 1, 1),
            heat_intensity="STRONG",
            last_calving_date=date(2025, 1, 1),  # > 60 days ago
        )
        assert result["success_probability"] >= 0.65

    def test_3a_required_keys(self):
        result = self._run(
            dob=date(2020, 1, 1),
            heat_intensity="STRONG",
        )
        for key in ("success_probability", "success_percent", "confidence",
                    "key_factors", "recommendation"):
            assert key in result, f"Missing key: {key}"

    def test_3a_success_percent_matches_probability(self):
        result = self._run(dob=date(2020, 1, 1), heat_intensity="STRONG")
        assert result["success_percent"] == int(round(result["success_probability"] * 100))

    # ── 3b. WEAK heat, old cow, recent calving ────────────────────────────────

    def test_3b_weak_heat_old_cow_recent_calving_lower_prob(self):
        """
        WEAK heat + age > 8 yrs + recent calving (<60 days):
            base 0.55 - age 0.08 - calving 0.05 = 0.42
        """
        result = self._run(
            dob=date(2010, 1, 1),           # ~16 years old
            heat_intensity="WEAK",
            last_calving_date=date(2026, 8, 1),  # 20 days ago (< 60)
        )
        assert result["success_probability"] <= 0.45

    def test_3b_key_factors_mention_age(self):
        result = self._run(
            dob=date(2010, 1, 1),
            heat_intensity="WEAK",
            last_calving_date=date(2026, 8, 1),
        )
        factors_text = " ".join(result["key_factors"]).lower()
        assert "age" in factors_text or "8" in factors_text

    # ── 3c. No prior calving ──────────────────────────────────────────────────

    def test_3c_no_prior_calving_no_penalty(self):
        """
        No prior calving → days_since_calving == 0 → calving penalty NOT applied.
        MODERATE heat, young cow: prob == 0.55 (no adjustments).
        """
        result = self._run(
            dob=date(2021, 1, 1),
            heat_intensity="MODERATE",
            last_calving_date=None,
        )
        assert result["success_probability"] == pytest.approx(0.55, abs=0.01)

    def test_3c_key_factors_mention_first_time(self):
        result = self._run(
            dob=date(2021, 1, 1),
            heat_intensity="MODERATE",
            last_calving_date=None,
        )
        factors_text = " ".join(result["key_factors"]).lower()
        assert "first" in factors_text or "no prior" in factors_text

    def test_probability_bounded_0_to_1(self):
        """Probability must always stay within [0.0, 1.0]."""
        for heat in ("WEAK", "MODERATE", "STRONG"):
            result = self._run(dob=date(2005, 1, 1), heat_intensity=heat)
            assert 0.0 <= result["success_probability"] <= 1.0, (
                f"Out-of-range probability for heat={heat}: {result['success_probability']}"
            )
