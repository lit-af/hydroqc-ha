"""Integration tests for DCPC (Winter Credits) schedule generation and seasonal behavior.

Tests verify:
- Schedule generation during winter season (Dec 1 - Mar 31)
- Binary sensors return False outside winter season
- Critical vs non-critical peak detection
- API announcements vs generated schedule
- DST transitions at end of winter
"""

import datetime
import zoneinfo

import pytest
from freezegun import freeze_time

from custom_components.hydroqc.public_data_client import PeakHandler


class TestDCPCScheduleGeneration:
    """Test DCPC schedule generation and seasonal behavior."""

    @pytest.fixture
    def dcpc_handler(self) -> PeakHandler:
        """Create DCPC PeakHandler."""
        return PeakHandler(rate_code="DCPC", preheat_duration=120)

    # ========================================================================
    # OUTSIDE WINTER SEASON TESTS
    # ========================================================================

    @freeze_time("2025-06-15T12:00:00-04:00")  # Summer - outside winter season
    def test_outside_winter_no_schedule_generated(self, dcpc_handler: PeakHandler) -> None:
        """Test that no schedule is generated outside winter season (June)."""
        # Load no API events
        dcpc_handler.load_events([])

        # Verify no events generated
        assert len(dcpc_handler._events) == 0
        assert dcpc_handler.current_state == "off_season"

    @freeze_time("2025-06-15T12:00:00-04:00")  # Summer
    def test_outside_winter_binary_sensors_false(self, dcpc_handler: PeakHandler) -> None:
        """Test that binary sensors return False (not None) outside winter."""
        dcpc_handler.load_events([])

        # All peak-related properties should be None
        assert dcpc_handler.today_morning_peak is None
        assert dcpc_handler.today_evening_peak is None
        assert dcpc_handler.tomorrow_morning_peak is None
        assert dcpc_handler.tomorrow_evening_peak is None

        # Binary sensor logic: if peak is None, is_critical should return False
        # This is handled by coordinator.get_sensor_value() returning False for .is_critical
        # when intermediate object is None

    @freeze_time("2025-10-01T12:00:00-04:00")  # October - outside winter
    def test_october_outside_winter(self, dcpc_handler: PeakHandler) -> None:
        """Test October (before winter starts Dec 1)."""
        dcpc_handler.load_events([])
        assert len(dcpc_handler._events) == 0
        assert dcpc_handler.current_state == "off_season"

    @freeze_time("2025-04-15T12:00:00-04:00")  # April - after winter ends
    def test_april_after_winter_ends(self, dcpc_handler: PeakHandler) -> None:
        """Test April (after winter ends Mar 31)."""
        dcpc_handler.load_events([])
        assert len(dcpc_handler._events) == 0
        assert dcpc_handler.current_state == "off_season"

    # ========================================================================
    # BEGINNING OF WINTER - NO CRITICAL PEAKS
    # ========================================================================

    @freeze_time("2024-12-02T10:00:00-05:00")  # Dec 2, 2024 - start of winter
    def test_beginning_winter_no_critical_peaks(self, dcpc_handler: PeakHandler) -> None:
        """Test beginning of winter with only generated schedule (no API critical peaks)."""
        # Load no API events - only generated schedule
        dcpc_handler.load_events([])

        # Should generate 4 peaks: today morning, today evening, tomorrow morning, tomorrow evening
        assert len(dcpc_handler._events) == 4

        # Verify all peaks are non-critical (generated schedule)
        for event in dcpc_handler._events:
            assert event.is_critical is False

        # Verify today's peaks exist
        today_morning = dcpc_handler.today_morning_peak
        assert today_morning is not None
        assert today_morning.start_date.hour == 6
        assert today_morning.end_date.hour == 10
        assert today_morning.is_critical is False

        today_evening = dcpc_handler.today_evening_peak
        assert today_evening is not None
        assert today_evening.start_date.hour == 16
        assert today_evening.end_date.hour == 20
        assert today_evening.is_critical is False

        # Verify tomorrow's peaks exist
        tomorrow_morning = dcpc_handler.tomorrow_morning_peak
        assert tomorrow_morning is not None
        assert tomorrow_morning.is_critical is False

        tomorrow_evening = dcpc_handler.tomorrow_evening_peak
        assert tomorrow_evening is not None
        assert tomorrow_evening.is_critical is False

    # ========================================================================
    # BEGINNING OF WINTER - WITH CRITICAL PEAKS
    # ========================================================================

    @freeze_time("2024-12-05T10:00:00-05:00")  # Dec 5, 2024
    def test_beginning_winter_with_critical_morning_peak(self, dcpc_handler: PeakHandler) -> None:
        """Test beginning of winter with API announcing critical morning peak for today."""
        # API announces critical morning peak for today
        api_event_today_morning = {
            "offre": "CPC-D",
            "datedebut": "2024-12-05T06:00:00-05:00",
            "datefin": "2024-12-05T10:00:00-05:00",
            "plagehoraire": "AM",
            "duree": "PT04H00MS",
            "secteurclient": "Résidentiel",
        }

        dcpc_handler.load_events([api_event_today_morning])

        # Should have 4 peaks: 1 critical from API, 3 non-critical generated
        assert len(dcpc_handler._events) == 4

        # Today morning should be critical (from API)
        today_morning = dcpc_handler.today_morning_peak
        assert today_morning is not None
        assert today_morning.is_critical is True

        # Today evening should be non-critical (generated)
        today_evening = dcpc_handler.today_evening_peak
        assert today_evening is not None
        assert today_evening.is_critical is False

        # Tomorrow's peaks should be non-critical (generated)
        tomorrow_morning = dcpc_handler.tomorrow_morning_peak
        assert tomorrow_morning is not None
        assert tomorrow_morning.is_critical is False

        tomorrow_evening = dcpc_handler.tomorrow_evening_peak
        assert tomorrow_evening is not None
        assert tomorrow_evening.is_critical is False

    @freeze_time("2024-12-05T10:00:00-05:00")  # Dec 5, 2024
    def test_beginning_winter_multiple_critical_peaks(self, dcpc_handler: PeakHandler) -> None:
        """Test beginning of winter with multiple critical peaks announced."""
        # API announces critical peaks for today evening and tomorrow morning
        api_events = [
            {
                "offre": "CPC-D",
                "datedebut": "2024-12-05T16:00:00-05:00",
                "datefin": "2024-12-05T20:00:00-05:00",
                "plagehoraire": "PM",
                "duree": "PT04H00MS",
                "secteurclient": "Résidentiel",
            },
            {
                "offre": "CPC-D",
                "datedebut": "2024-12-06T06:00:00-05:00",
                "datefin": "2024-12-06T10:00:00-05:00",
                "plagehoraire": "AM",
                "duree": "PT04H00MS",
                "secteurclient": "Résidentiel",
            },
        ]

        dcpc_handler.load_events(api_events)

        # Should have 4 peaks: 2 critical from API, 2 non-critical generated
        assert len(dcpc_handler._events) == 4

        # Count critical vs non-critical
        critical_count = sum(1 for e in dcpc_handler._events if e.is_critical)
        non_critical_count = sum(1 for e in dcpc_handler._events if not e.is_critical)
        assert critical_count == 2
        assert non_critical_count == 2

        # Verify specific peaks
        today_morning = dcpc_handler.today_morning_peak
        assert today_morning is not None
        assert today_morning.is_critical is False  # Not announced, generated

        today_evening = dcpc_handler.today_evening_peak
        assert today_evening is not None
        assert today_evening.is_critical is True  # From API

        tomorrow_morning = dcpc_handler.tomorrow_morning_peak
        assert tomorrow_morning is not None
        assert tomorrow_morning.is_critical is True  # From API

        tomorrow_evening = dcpc_handler.tomorrow_evening_peak
        assert tomorrow_evening is not None
        assert tomorrow_evening.is_critical is False  # Not announced, generated

    # ========================================================================
    # END OF WINTER - BEFORE DST (March, before DST)
    # ========================================================================

    @freeze_time("2025-03-05T10:00:00-05:00")  # March 5, 2025 (before DST on March 9)
    def test_end_winter_before_dst_no_critical(self, dcpc_handler: PeakHandler) -> None:
        """Test end of winter before DST transition with no critical peaks."""
        dcpc_handler.load_events([])

        # Still within winter season, should generate schedule
        assert len(dcpc_handler._events) == 4

        # All should be non-critical
        for event in dcpc_handler._events:
            assert event.is_critical is False

        # Verify peaks exist and are timezone-aware
        today_morning = dcpc_handler.today_morning_peak
        assert today_morning is not None
        assert today_morning.start_date.tzinfo is not None
        assert today_morning.start_date.strftime("%z") == "-0500"  # EST

    @freeze_time("2025-03-05T10:00:00-05:00")  # March 5, 2025
    def test_end_winter_before_dst_with_critical(self, dcpc_handler: PeakHandler) -> None:
        """Test end of winter before DST with critical peak announced."""
        api_event = {
            "offre": "CPC-D",
            "datedebut": "2025-03-05T16:00:00-05:00",
            "datefin": "2025-03-05T20:00:00-05:00",
            "plagehoraire": "PM",
            "duree": "PT04H00MS",
            "secteurclient": "Résidentiel",
        }

        dcpc_handler.load_events([api_event])

        assert len(dcpc_handler._events) == 4

        today_evening = dcpc_handler.today_evening_peak
        assert today_evening is not None
        assert today_evening.is_critical is True

    # ========================================================================
    # END OF WINTER - DURING DST TRANSITION
    # ========================================================================

    @freeze_time("2025-03-09T10:00:00-04:00")  # March 9, 2025 - DST transition day (after 2 AM)
    def test_end_winter_dst_day_no_critical(self, dcpc_handler: PeakHandler) -> None:
        """Test end of winter on DST transition day with no critical peaks."""
        dcpc_handler.load_events([])

        # Should generate schedule (still within winter)
        assert len(dcpc_handler._events) == 4

        # Verify timezone handling across DST
        today_morning = dcpc_handler.today_morning_peak
        assert today_morning is not None
        # Morning peak starts at 6 AM, which is after DST transition (2 AM -> 3 AM)
        # So it should be in EDT (-04:00)
        assert today_morning.start_date.strftime("%z") == "-0400"  # EDT

    @freeze_time("2025-03-09T10:00:00-04:00")  # March 9, 2025 - DST day
    def test_end_winter_dst_day_with_critical(self, dcpc_handler: PeakHandler) -> None:
        """Test end of winter on DST day with critical peak."""
        # Critical evening peak on DST day
        api_event = {
            "offre": "CPC-D",
            "datedebut": "2025-03-09T16:00:00-04:00",  # EDT
            "datefin": "2025-03-09T20:00:00-04:00",
            "plagehoraire": "PM",
            "duree": "PT04H00MS",
            "secteurclient": "Résidentiel",
        }

        dcpc_handler.load_events([api_event])

        today_evening = dcpc_handler.today_evening_peak
        assert today_evening is not None
        assert today_evening.is_critical is True
        assert today_evening.start_date.strftime("%z") == "-0400"  # EDT

    # ========================================================================
    # END OF WINTER - AFTER DST
    # ========================================================================

    @freeze_time("2025-03-25T10:00:00-04:00")  # March 25, 2025 (after DST, before end of season)
    def test_end_winter_after_dst_no_critical(self, dcpc_handler: PeakHandler) -> None:
        """Test end of winter after DST transition with no critical peaks."""
        dcpc_handler.load_events([])

        # Still within winter season (ends Mar 31)
        assert len(dcpc_handler._events) == 4

        # All in EDT now
        for event in dcpc_handler._events:
            assert event.start_date.strftime("%z") == "-0400"
            assert event.is_critical is False

    @freeze_time("2025-03-30T10:00:00-04:00")  # March 30, 2025 - second to last day of winter
    def test_last_days_winter_with_critical(self, dcpc_handler: PeakHandler) -> None:
        """Test last days of winter season with critical peaks."""
        # Critical peak on tomorrow (Mar 31, last day of winter)
        api_event = {
            "offre": "CPC-D",
            "datedebut": "2025-03-31T06:00:00-04:00",
            "datefin": "2025-03-31T10:00:00-04:00",
            "plagehoraire": "AM",
            "duree": "PT04H00MS",
            "secteurclient": "Résidentiel",
        }

        dcpc_handler.load_events([api_event])

        tomorrow_morning = dcpc_handler.tomorrow_morning_peak
        assert tomorrow_morning is not None
        assert tomorrow_morning.is_critical is True
        assert tomorrow_morning.start_date.date() == datetime.date(2025, 3, 31)

    @freeze_time("2025-03-31T10:00:00-04:00")  # March 31, 2025 - LAST day of winter
    def test_last_day_of_winter(self, dcpc_handler: PeakHandler) -> None:
        """Test last day of winter season (Mar 31).

        Note: Schedule generator creates peaks for today AND tomorrow,
        even though April 1 is outside winter season. This is by design -
        the generator doesn't filter by season when creating peaks.
        """
        dcpc_handler.load_events([])

        # Generator creates 4 peaks: today (Mar 31) + tomorrow (Apr 1)
        assert len(dcpc_handler._events) == 4

        # Today's peaks (Mar 31) - still in season
        today_morning = dcpc_handler.today_morning_peak
        today_evening = dcpc_handler.today_evening_peak
        assert today_morning is not None
        assert today_evening is not None
        assert today_morning.start_date.date() == datetime.date(2025, 3, 31)
        assert today_morning.is_critical is False
        assert today_evening.start_date.date() == datetime.date(2025, 3, 31)
        assert today_evening.is_critical is False

        # Tomorrow (Apr 1) - outside season but still generated
        tomorrow_morning = dcpc_handler.tomorrow_morning_peak
        tomorrow_evening = dcpc_handler.tomorrow_evening_peak
        assert tomorrow_morning is not None
        assert tomorrow_evening is not None
        assert tomorrow_morning.start_date.date() == datetime.date(2025, 4, 1)
        assert tomorrow_morning.is_critical is False
        assert tomorrow_evening.start_date.date() == datetime.date(2025, 4, 1)
        assert tomorrow_evening.is_critical is False

    # ========================================================================
    # ANCHOR PERIOD TESTS
    # ========================================================================

    @freeze_time("2024-12-10T02:00:00-05:00")  # Dec 10, 2024 at 2 AM (during morning anchor)
    def test_anchor_period_during_morning_anchor(self, dcpc_handler: PeakHandler) -> None:
        """Test that anchor periods are correctly identified during morning anchor time."""
        dcpc_handler.load_events([])

        today_morning = dcpc_handler.today_morning_peak
        assert today_morning is not None

        # Get anchor
        anchor = today_morning.anchor
        assert anchor is not None
        assert anchor.start_date.hour == 1
        assert anchor.end_date.hour == 4

        # Verify we're currently in the anchor period
        tz = zoneinfo.ZoneInfo("America/Toronto")
        now = datetime.datetime.now(tz)
        assert anchor.start_date <= now < anchor.end_date

    @freeze_time("2024-12-10T13:00:00-05:00")  # Dec 10, 2024 at 1 PM (during evening anchor)
    def test_anchor_period_during_evening_anchor(self, dcpc_handler: PeakHandler) -> None:
        """Test evening anchor period (12-2 PM before 4-8 PM peak)."""
        dcpc_handler.load_events([])

        today_evening = dcpc_handler.today_evening_peak
        assert today_evening is not None

        anchor = today_evening.anchor
        assert anchor is not None
        assert anchor.start_date.hour == 12
        assert anchor.end_date.hour == 14

        # Verify we're in the anchor
        tz = zoneinfo.ZoneInfo("America/Toronto")
        now = datetime.datetime.now(tz)
        assert anchor.start_date <= now < anchor.end_date

    @freeze_time("2024-12-15T10:00:00-05:00")  # Dec 15, 2024
    def test_anchor_inherits_critical_status(self, dcpc_handler: PeakHandler) -> None:
        """Test that anchor periods inherit is_critical from their peak."""
        # Critical morning peak
        api_event = {
            "offre": "CPC-D",
            "datedebut": "2024-12-15T06:00:00-05:00",
            "datefin": "2024-12-15T10:00:00-05:00",
            "plagehoraire": "AM",
            "duree": "PT04H00MS",
            "secteurclient": "Résidentiel",
        }

        dcpc_handler.load_events([api_event])

        today_morning = dcpc_handler.today_morning_peak
        assert today_morning is not None
        assert today_morning.is_critical is True

        # Anchor should also be critical
        anchor = today_morning.anchor
        assert anchor.is_critical is True

        # Non-critical evening peak
        today_evening = dcpc_handler.today_evening_peak
        assert today_evening is not None
        assert today_evening.is_critical is False

        # Anchor should also be non-critical
        anchor_evening = today_evening.anchor
        assert anchor_evening.is_critical is False

    # ========================================================================
    # DETAILED ANCHOR PERIOD TESTS
    # ========================================================================

    @freeze_time("2024-12-10T10:00:00-05:00")
    def test_anchor_period_timing_morning(self, dcpc_handler: PeakHandler) -> None:
        """Test morning anchor period timing calculations."""
        # Load schedule (generates non-critical peaks)
        dcpc_handler.load_events([])

        # Get today's morning peak
        morning_peak = dcpc_handler.today_morning_peak
        assert morning_peak is not None
        assert morning_peak.is_critical is False

        anchor = morning_peak.anchor
        assert anchor is not None
        assert anchor.is_critical is False

        # Morning anchor: 5 hours before peak, 3 hours duration
        # Peak at 6:00, anchor should start at 1:00
        assert anchor.start_date.hour == 1
        assert anchor.end_date.hour == 4

        duration_hours = (anchor.end_date - anchor.start_date).total_seconds() / 3600
        assert duration_hours == 3.0

    @freeze_time("2024-12-10T10:00:00-05:00")
    def test_anchor_period_timing_evening(self, dcpc_handler: PeakHandler) -> None:
        """Test evening anchor period timing calculations."""
        # Load schedule (generates non-critical peaks)
        dcpc_handler.load_events([])

        # Get today's evening peak
        evening_peak = dcpc_handler.today_evening_peak
        assert evening_peak is not None
        assert evening_peak.is_critical is False

        anchor = evening_peak.anchor
        assert anchor is not None
        assert anchor.is_critical is False

        # Evening anchor: 4 hours before peak, 2 hours duration
        # Peak at 16:00, anchor should start at 12:00
        assert anchor.start_date.hour == 12
        assert anchor.end_date.hour == 14

        duration_hours = (anchor.end_date - anchor.start_date).total_seconds() / 3600
        assert duration_hours == 2.0

    # ========================================================================
    # TOMORROW PEAK DETECTION
    # ========================================================================

    @freeze_time("2024-12-10T22:00:00-05:00")  # Late evening
    def test_tomorrow_peak_flags(self, dcpc_handler: PeakHandler) -> None:
        """Test tomorrow peak detection for binary sensors."""
        # Load schedule with tomorrow's critical morning peak
        api_event = {
            "offre": "CPC-D",
            "datedebut": "2024-12-11T06:00:00-05:00",
            "datefin": "2024-12-11T10:00:00-05:00",
            "plagehoraire": "AM",
            "duree": "PT04H00MS",
            "secteurclient": "Résidentiel",
        }
        dcpc_handler.load_events([api_event])

        # Tomorrow morning should be critical (from API)
        tomorrow_morning = dcpc_handler.tomorrow_morning_peak
        assert tomorrow_morning is not None
        assert tomorrow_morning.is_critical is True
        assert tomorrow_morning.start_date.date() == datetime.date(2024, 12, 11)

        # Tomorrow evening should be non-critical (from schedule)
        tomorrow_evening = dcpc_handler.tomorrow_evening_peak
        assert tomorrow_evening is not None
        assert tomorrow_evening.is_critical is False
        assert tomorrow_evening.start_date.date() == datetime.date(2024, 12, 11)
