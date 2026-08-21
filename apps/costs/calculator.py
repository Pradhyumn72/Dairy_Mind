"""
costs.calculator
~~~~~~~~~~~~~~~~

FeedYieldCalculator
-------------------
All ROI / cost-per-litre / profit business logic lives here, decoupled from
Django views so it can be called from Celery tasks, management commands, or
tests without touching HTTP.

Public methods
~~~~~~~~~~~~~~
calculate_monthly_roi(cattle_id, month, year) → dict
    Full P&L breakdown for a single cattle in the given month.
    Persists result to CostSummary (upsert).

farm_wide_summary(month, year) → dict
    Aggregates calculate_monthly_roi() for every active cattle, returns
    farm totals plus top-5 / bottom-5 ranked by profit.
    Persists per-cattle CostSummary rows as a side-effect.

All monetary values are in INR.  The milk price is read from
``django.conf.settings.MILK_PRICE_PER_LITRE`` (default 55).
"""
from __future__ import annotations

import logging
from decimal import ROUND_HALF_UP, Decimal
from typing import TypedDict

from django.conf import settings
from django.db.models import Sum

logger = logging.getLogger(__name__)

# ── Types ─────────────────────────────────────────────────────────────────────

class CattleROI(TypedDict):
    cattle_id:          int
    tag_number:         str
    name:               str
    month:              int
    year:               int
    total_feed_cost:    float   # INR
    total_milk_litres:  float
    milk_price_per_litre: float # INR / litre (setting value used)
    revenue:            float   # INR
    profit:             float   # INR (negative = loss)
    cost_per_litre:     float | None   # None when no milk produced
    profit_margin:      float | None   # 0–1 ratio; None when revenue == 0
    roi_ratio:          float | None   # revenue / feed_cost; None when cost == 0
    has_feed_data:      bool
    has_milk_data:      bool


class FarmWideSummary(TypedDict):
    month:              int
    year:               int
    milk_price_per_litre: float
    cattle_count:       int
    farm_total_feed_cost:  float
    farm_total_milk_litres: float
    farm_total_revenue:    float
    farm_total_profit:     float
    top_5_profitable:   list[CattleROI]
    bottom_5_profitable: list[CattleROI]
    all_cattle:         list[CattleROI]


# ── Helper ────────────────────────────────────────────────────────────────────

def _d(value) -> Decimal:
    """Coerce a numeric value to a Decimal rounded to 4 d.p."""
    return Decimal(str(value or 0)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _f(value) -> float:
    """Round a Decimal / float to 2 d.p. and return a plain float."""
    return float(Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


# ── Main calculator class ─────────────────────────────────────────────────────

class FeedYieldCalculator:
    """
    Stateless calculator for feed cost vs milk yield ROI.

    Instantiate once and reuse, or call class-level static methods directly.

    Parameters
    ----------
    milk_price_per_litre : float | None
        Override the setting value for this instance.  Defaults to
        ``settings.MILK_PRICE_PER_LITRE`` (55 INR).
    """

    def __init__(self, milk_price_per_litre: float | None = None) -> None:
        self.milk_price = float(
            milk_price_per_litre
            if milk_price_per_litre is not None
            else getattr(settings, "MILK_PRICE_PER_LITRE", 55.0)
        )

    # ── Public: per-cattle monthly ROI ────────────────────────────────────────

    def calculate_monthly_roi(
        self,
        cattle_id: int,
        month: int,
        year: int,
    ) -> CattleROI:
        """
        Calculate full P&L for *cattle_id* in the given *month* / *year*.

        Steps
        -----
        1. Sum FeedLog.total_cost for the period → ``total_feed_cost``
        2. Sum MilkLog.total_litres for the period → ``total_milk_litres``
        3. Derive revenue, profit, cost_per_litre, profit_margin, roi_ratio
        4. Upsert a CostSummary record
        5. Return the full metric dict

        Parameters
        ----------
        cattle_id : int  — PK of the Cattle record
        month     : int  — 1–12
        year      : int  — four-digit year

        Returns
        -------
        CattleROI dict

        Raises
        ------
        django.core.exceptions.ObjectDoesNotExist
            When no Cattle with the given PK exists.
        """
        from apps.cattle.models import Cattle
        from apps.costs.models import CostSummary, FeedLog
        from apps.milk.models import MilkLog

        cattle = Cattle.objects.get(pk=cattle_id)

        logger.debug(
            "[FeedYieldCalculator] cattle=%s month=%02d/%d",
            cattle.tag_number, month, year,
        )

        # ── 1. Feed cost ──────────────────────────────────────────────────────
        feed_agg = FeedLog.objects.filter(
            cattle=cattle,
            date__year=year,
            date__month=month,
        ).aggregate(total=Sum("total_cost"))
        total_feed_cost = _d(feed_agg["total"] or 0)
        has_feed_data   = total_feed_cost > 0

        # ── 2. Milk yield ─────────────────────────────────────────────────────
        milk_agg = MilkLog.objects.filter(
            cattle=cattle,
            date__year=year,
            date__month=month,
        ).aggregate(total=Sum("total_litres"))
        total_milk_litres = _d(milk_agg["total"] or 0)
        has_milk_data     = total_milk_litres > 0

        # ── 3. Derived metrics ────────────────────────────────────────────────
        price      = _d(self.milk_price)
        revenue    = (total_milk_litres * price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        profit     = (revenue - total_feed_cost).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        cost_per_litre: float | None = None
        if total_milk_litres > 0:
            cost_per_litre = _f(total_feed_cost / total_milk_litres)

        profit_margin: float | None = None
        if revenue > 0:
            profit_margin = _f(profit / revenue)

        roi_ratio: float | None = None
        if total_feed_cost > 0:
            roi_ratio = _f(revenue / total_feed_cost)

        # ── 4. Upsert CostSummary ─────────────────────────────────────────────
        CostSummary.objects.update_or_create(
            cattle=cattle,
            month=month,
            year=year,
            defaults={
                "total_feed_cost":   total_feed_cost,
                "total_milk_litres": total_milk_litres,
                "cost_per_litre":    _d(cost_per_litre) if cost_per_litre is not None else None,
                "profit_margin":     _d(profit_margin)  if profit_margin  is not None else None,
            },
        )

        result: CattleROI = {
            "cattle_id":           cattle.pk,
            "tag_number":          cattle.tag_number,
            "name":                cattle.name,
            "month":               month,
            "year":                year,
            "total_feed_cost":     _f(total_feed_cost),
            "total_milk_litres":   _f(total_milk_litres),
            "milk_price_per_litre": self.milk_price,
            "revenue":             _f(revenue),
            "profit":              _f(profit),
            "cost_per_litre":      cost_per_litre,
            "profit_margin":       profit_margin,
            "roi_ratio":           roi_ratio,
            "has_feed_data":       has_feed_data,
            "has_milk_data":       has_milk_data,
        }

        logger.info(
            "[FeedYieldCalculator] %s %02d/%d → feed=%.2f milk=%.2fL "
            "revenue=%.2f profit=%.2f",
            cattle.tag_number, month, year,
            result["total_feed_cost"], result["total_milk_litres"],
            result["revenue"], result["profit"],
        )
        return result

    # ── Public: farm-wide monthly summary ─────────────────────────────────────

    def farm_wide_summary(self, month: int, year: int) -> FarmWideSummary:
        """
        Aggregate ROI for every active cattle in *month* / *year* and return
        farm totals plus ranked top-5 / bottom-5 by profit.

        Calls ``calculate_monthly_roi()`` per cattle, which upserts each
        CostSummary row as a side-effect.

        Parameters
        ----------
        month : int  — 1–12
        year  : int  — four-digit year

        Returns
        -------
        FarmWideSummary dict
        """
        from apps.cattle.models import Cattle

        active_cattle = list(Cattle.objects.filter(is_active=True))
        logger.info(
            "[FeedYieldCalculator] farm_wide_summary: %d active cattle, %02d/%d",
            len(active_cattle), month, year,
        )

        all_results: list[CattleROI] = []
        for cattle in active_cattle:
            try:
                roi = self.calculate_monthly_roi(
                    cattle_id=cattle.pk,
                    month=month,
                    year=year,
                )
                all_results.append(roi)
            except Exception as exc:
                logger.error(
                    "[FeedYieldCalculator] Error for cattle=%s: %s",
                    cattle.tag_number, exc, exc_info=True,
                )

        # ── Farm-level totals ─────────────────────────────────────────────────
        farm_feed_cost    = _f(sum(r["total_feed_cost"]   for r in all_results))
        farm_milk_litres  = _f(sum(r["total_milk_litres"] for r in all_results))
        farm_revenue      = _f(sum(r["revenue"]           for r in all_results))
        farm_profit       = _f(sum(r["profit"]            for r in all_results))

        # ── Rank by profit (None profit treated as -∞ for sorting) ────────────
        ranked = sorted(
            all_results,
            key=lambda r: r["profit"] if r["profit"] is not None else float("-inf"),
            reverse=True,
        )
        top_5    = ranked[:5]
        bottom_5 = list(reversed(ranked[-5:])) if len(ranked) >= 5 else list(reversed(ranked))

        summary: FarmWideSummary = {
            "month":                    month,
            "year":                     year,
            "milk_price_per_litre":     self.milk_price,
            "cattle_count":             len(all_results),
            "farm_total_feed_cost":     farm_feed_cost,
            "farm_total_milk_litres":   farm_milk_litres,
            "farm_total_revenue":       farm_revenue,
            "farm_total_profit":        farm_profit,
            "top_5_profitable":         top_5,
            "bottom_5_profitable":      bottom_5,
            "all_cattle":               all_results,
        }

        logger.info(
            "[FeedYieldCalculator] farm_wide_summary %02d/%d → "
            "cattle=%d feed=%.2f revenue=%.2f profit=%.2f",
            month, year, len(all_results),
            farm_feed_cost, farm_revenue, farm_profit,
        )
        return summary
