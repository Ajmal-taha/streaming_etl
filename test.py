"""
test.py
--------
Tests for the event-driven ETL pipeline.

Split into two suites:
  ── Unit tests        No DB needed. Tests pure Python logic in isolation.
  ── Integration tests Needs LocalDB running with SalesDB set up.
                       Skipped automatically if the DB is unreachable.

Run all tests:
    python test.py

Run only unit tests (no DB required):
    python -m unittest TestCategorize TestTransform -v

Run only integration tests:
    python -m unittest TestIntegration -v
"""

import sys
import time
import types
import unittest
import unittest.mock as mock

import pandas as pd


# ─────────────────────────────────────────────────────────────────────────────
# Import the module under test.
# We mock pyodbc and matplotlib so the import works without those dependencies.
# ─────────────────────────────────────────────────────────────────────────────
sys.modules.setdefault("pyodbc", mock.MagicMock())
sys.modules.setdefault("matplotlib", mock.MagicMock())
sys.modules.setdefault("matplotlib.pyplot", mock.MagicMock())
sys.modules.setdefault("matplotlib.animation", mock.MagicMock())

import watch_and_visualize as etl   # noqa: E402  (import after mock setup)


# ═════════════════════════════════════════════════════════════════════════════
# UNIT TESTS — pure logic, no DB
# ═════════════════════════════════════════════════════════════════════════════

class TestCategorize(unittest.TestCase):
    """Tests for the categorize() spend-bucketing function."""

    def test_high_threshold_exact(self):
        self.assertEqual(etl.categorize(500), "High")

    def test_high_above_threshold(self):
        self.assertEqual(etl.categorize(999.99), "High")

    def test_medium_threshold_exact(self):
        self.assertEqual(etl.categorize(200), "Medium")

    def test_medium_below_high(self):
        self.assertEqual(etl.categorize(499.99), "Medium")

    def test_low_just_below_medium(self):
        self.assertEqual(etl.categorize(199.99), "Low")

    def test_low_zero_spend(self):
        self.assertEqual(etl.categorize(0), "Low")

    def test_low_small_amount(self):
        self.assertEqual(etl.categorize(10), "Low")


class TestTransform(unittest.TestCase):
    """
    Tests for EventDrivenWatcher._get_category_counts().
    The watcher is created with a mocked connection so no DB is touched.
    """

    def _make_watcher(self, rows):
        """
        Build a watcher whose self.orders is pre-populated with `rows`
        (list of dicts with keys order_id, customer_id, amount).
        Skips __init__ entirely to avoid DB calls.
        """
        w = etl.EventDrivenWatcher.__new__(etl.EventDrivenWatcher)
        w.last_seen_id = 0
        w.new_data     = False
        w.orders       = pd.DataFrame(rows, columns=["order_id", "customer_id", "amount"])
        return w

    # ── empty state ───────────────────────────────────────────────────────────
    def test_empty_orders_returns_zero_counts(self):
        w = self._make_watcher([])
        counts = w._get_category_counts()
        self.assertEqual(counts["Low"],    0)
        self.assertEqual(counts["Medium"], 0)
        self.assertEqual(counts["High"],   0)

    # ── single customer per category ──────────────────────────────────────────
    def test_single_high_spender(self):
        w = self._make_watcher([
            {"order_id": 1, "customer_id": 1, "amount": 600.00}
        ])
        counts = w._get_category_counts()
        self.assertEqual(counts["High"],   1)
        self.assertEqual(counts["Medium"], 0)
        self.assertEqual(counts["Low"],    0)

    def test_single_medium_spender(self):
        w = self._make_watcher([
            {"order_id": 1, "customer_id": 1, "amount": 250.00}
        ])
        counts = w._get_category_counts()
        self.assertEqual(counts["Medium"], 1)

    def test_single_low_spender(self):
        w = self._make_watcher([
            {"order_id": 1, "customer_id": 1, "amount": 50.00}
        ])
        counts = w._get_category_counts()
        self.assertEqual(counts["Low"], 1)

    # ── multiple orders, same customer — spend must be summed ─────────────────
    def test_multiple_orders_same_customer_summed(self):
        """Customer 1 has two orders totalling $550 → High."""
        w = self._make_watcher([
            {"order_id": 1, "customer_id": 1, "amount": 300.00},
            {"order_id": 2, "customer_id": 1, "amount": 250.00},
        ])
        counts = w._get_category_counts()
        self.assertEqual(counts["High"],   1)
        self.assertEqual(counts["Medium"], 0)
        self.assertEqual(counts["Low"],    0)

    def test_customer_crosses_threshold_with_second_order(self):
        """Customer starts Low, second order pushes them into Medium."""
        w = self._make_watcher([
            {"order_id": 1, "customer_id": 2, "amount": 100.00},
            {"order_id": 2, "customer_id": 2, "amount": 150.00},
        ])
        counts = w._get_category_counts()
        self.assertEqual(counts["Medium"], 1)
        self.assertEqual(counts["Low"],    0)

    # ── mixed customers ───────────────────────────────────────────────────────
    def test_mixed_categories(self):
        w = self._make_watcher([
            {"order_id": 1, "customer_id": 1, "amount": 600.00},   # High
            {"order_id": 2, "customer_id": 2, "amount": 300.00},   # Medium
            {"order_id": 3, "customer_id": 3, "amount": 50.00},    # Low
            {"order_id": 4, "customer_id": 4, "amount": 80.00},    # Low
        ])
        counts = w._get_category_counts()
        self.assertEqual(counts["High"],   1)
        self.assertEqual(counts["Medium"], 1)
        self.assertEqual(counts["Low"],    2)

    # ── boundary values ───────────────────────────────────────────────────────
    def test_exactly_at_high_boundary(self):
        w = self._make_watcher([
            {"order_id": 1, "customer_id": 1, "amount": 500.00}
        ])
        self.assertEqual(w._get_category_counts()["High"], 1)

    def test_exactly_at_medium_boundary(self):
        w = self._make_watcher([
            {"order_id": 1, "customer_id": 1, "amount": 200.00}
        ])
        self.assertEqual(w._get_category_counts()["Medium"], 1)

    def test_one_cent_below_medium_is_low(self):
        w = self._make_watcher([
            {"order_id": 1, "customer_id": 1, "amount": 199.99}
        ])
        self.assertEqual(w._get_category_counts()["Low"], 1)

    # ── new_data flag ─────────────────────────────────────────────────────────
    def test_new_data_flag_starts_false(self):
        w = self._make_watcher([])
        self.assertFalse(w.new_data)

    def test_new_data_flag_set_by_run_etl(self):
        """_run_etl should set new_data = True after processing."""
        w = self._make_watcher([])

        # Fake cursor that returns an empty new-rows query
        fake_cursor = mock.MagicMock()
        empty_df    = pd.DataFrame(columns=["order_id", "customer_id", "amount"])

        with mock.patch("pandas.read_sql", return_value=empty_df):
            w._run_etl(fake_cursor)

        self.assertTrue(w.new_data)

    def test_run_etl_resets_dirty_flag(self):
        """_run_etl must call UPDATE change_log SET dirty = 0."""
        w = self._make_watcher([])
        fake_cursor = mock.MagicMock()
        empty_df    = pd.DataFrame(columns=["order_id", "customer_id", "amount"])

        with mock.patch("pandas.read_sql", return_value=empty_df):
            w._run_etl(fake_cursor)

        # Verify that the cursor was called with the reset query
        calls = [str(call) for call in fake_cursor.execute.call_args_list]
        self.assertTrue(
            any("dirty = 0" in c for c in calls),
            "dirty flag was never reset to 0"
        )

    def test_last_seen_id_advances_after_etl(self):
        """After _run_etl, last_seen_id should equal the max order_id fetched."""
        w           = self._make_watcher([])
        fake_cursor = mock.MagicMock()
        new_rows    = pd.DataFrame([
            {"order_id": 10, "customer_id": 1, "amount": 100.00},
            {"order_id": 11, "customer_id": 2, "amount": 200.00},
        ])

        with mock.patch("pandas.read_sql", return_value=new_rows):
            w._run_etl(fake_cursor)

        self.assertEqual(w.last_seen_id, 11)

    def test_only_new_rows_are_fetched(self):
        """
        Extract query must use last_seen_id as the WHERE filter so already-
        processed rows are not reprocessed.
        """
        w              = self._make_watcher([])
        w.last_seen_id = 5        # pretend we already processed up to id 5
        fake_cursor    = mock.MagicMock()
        empty_df       = pd.DataFrame(columns=["order_id", "customer_id", "amount"])

        with mock.patch("pandas.read_sql", return_value=empty_df) as mock_read:
            w._run_etl(fake_cursor)
            _, kwargs = mock_read.call_args
            params = kwargs.get("params") or mock_read.call_args[0][2]
            self.assertEqual(params[0], 5, "fetch query should filter by last_seen_id=5")


# ═════════════════════════════════════════════════════════════════════════════
# INTEGRATION TESTS — require LocalDB + SalesDB to be running
# ═════════════════════════════════════════════════════════════════════════════

# Try to import real pyodbc (not the mock at the top of this file)
try:
    import importlib
    real_pyodbc = importlib.import_module("pyodbc")
    _db_available = True
except Exception:
    _db_available = False

DB_SKIP_REASON = (
    "LocalDB not reachable — run SSMS, ensure SalesDB exists, "
    "then re-run the full test suite."
)


@unittest.skipUnless(_db_available, DB_SKIP_REASON)
class TestIntegration(unittest.TestCase):
    """
    End-to-end tests against a real SalesDB instance.
    Each test cleans up after itself so they can run in any order.
    """

    CONN_STR = etl.CONN_STR

    @classmethod
    def setUpClass(cls):
        """Verify we can actually connect before attempting any test."""
        try:
            cls.conn = real_pyodbc.connect(cls.CONN_STR, autocommit=True)
        except Exception as e:
            raise unittest.SkipTest(f"DB connection failed: {e}")

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def setUp(self):
        """Clear orders and reset dirty flag before each test."""
        cur = self.conn.cursor()
        cur.execute("DELETE FROM orders")
        cur.execute("UPDATE change_log SET dirty = 0 WHERE id = 1")

    # ── connection ────────────────────────────────────────────────────────────
    def test_db_connection(self):
        cur = self.conn.cursor()
        cur.execute("SELECT 1")
        self.assertEqual(cur.fetchone()[0], 1)

    # ── schema ────────────────────────────────────────────────────────────────
    def test_orders_table_exists(self):
        cur = self.conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_NAME = 'orders'"
        )
        self.assertEqual(cur.fetchone()[0], 1)

    def test_change_log_table_exists(self):
        cur = self.conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_NAME = 'change_log'"
        )
        self.assertEqual(cur.fetchone()[0], 1)

    def test_trigger_exists(self):
        cur = self.conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM sys.triggers "
            "WHERE name = 'trg_orders_after_insert'"
        )
        self.assertEqual(cur.fetchone()[0], 1, "Trigger not found — did you run setup_database.sql?")

    # ── trigger behaviour ─────────────────────────────────────────────────────
    def test_insert_sets_dirty_flag(self):
        """Inserting a row into orders should flip change_log.dirty to 1."""
        cur = self.conn.cursor()
        cur.execute("INSERT INTO orders (customer_id, amount) VALUES (99, 100.00)")

        cur.execute("SELECT dirty FROM change_log WHERE id = 1")
        self.assertEqual(cur.fetchone()[0], 1, "Trigger did not set dirty = 1")

    def test_dirty_flag_starts_clean(self):
        """After setUp resets the flag it should be 0."""
        cur = self.conn.cursor()
        cur.execute("SELECT dirty FROM change_log WHERE id = 1")
        self.assertEqual(cur.fetchone()[0], 0)

    def test_multiple_inserts_flag_stays_1(self):
        """Two inserts in a row — dirty stays 1 until Python resets it."""
        cur = self.conn.cursor()
        cur.execute("INSERT INTO orders (customer_id, amount) VALUES (1, 50.00)")
        cur.execute("INSERT INTO orders (customer_id, amount) VALUES (2, 60.00)")
        cur.execute("SELECT dirty FROM change_log WHERE id = 1")
        self.assertEqual(cur.fetchone()[0], 1)

    # ── ETL watcher ───────────────────────────────────────────────────────────
    def test_watcher_loads_existing_orders_on_startup(self):
        cur = self.conn.cursor()
        cur.execute("INSERT INTO orders (customer_id, amount) VALUES (1, 100.00)")
        cur.execute("INSERT INTO orders (customer_id, amount) VALUES (2, 200.00)")

        watcher = etl.EventDrivenWatcher(self.CONN_STR)
        self.assertEqual(len(watcher.orders), 2)

    def test_watcher_last_seen_id_set_on_startup(self):
        cur = self.conn.cursor()
        cur.execute("INSERT INTO orders (customer_id, amount) VALUES (1, 100.00)")

        watcher = etl.EventDrivenWatcher(self.CONN_STR)
        self.assertGreater(watcher.last_seen_id, 0)

    def test_run_etl_fetches_only_new_rows(self):
        """
        Insert 2 rows, build watcher (picks them up), insert 1 more.
        _run_etl should fetch exactly that 1 new row.
        """
        cur = self.conn.cursor()
        cur.execute("INSERT INTO orders (customer_id, amount) VALUES (1, 100.00)")
        cur.execute("INSERT INTO orders (customer_id, amount) VALUES (2, 200.00)")

        watcher = etl.EventDrivenWatcher(self.CONN_STR)
        orders_before = len(watcher.orders)

        cur.execute("INSERT INTO orders (customer_id, amount) VALUES (3, 300.00)")
        watcher._run_etl(cur)

        self.assertEqual(len(watcher.orders), orders_before + 1)

    def test_run_etl_resets_dirty_flag_in_db(self):
        cur = self.conn.cursor()
        cur.execute("INSERT INTO orders (customer_id, amount) VALUES (1, 100.00)")
        watcher = etl.EventDrivenWatcher(self.CONN_STR)
        watcher._run_etl(cur)

        cur.execute("SELECT dirty FROM change_log WHERE id = 1")
        self.assertEqual(cur.fetchone()[0], 0)

    def test_full_event_cycle(self):
        """
        Simulate the full event loop:
        insert → dirty becomes 1 → ETL runs → dirty resets to 0 → new_data = True
        """
        cur     = self.conn.cursor()
        watcher = etl.EventDrivenWatcher(self.CONN_STR)

        # Insert triggers the flag
        cur.execute("INSERT INTO orders (customer_id, amount) VALUES (5, 450.00)")
        cur.execute("SELECT dirty FROM change_log WHERE id = 1")
        self.assertEqual(cur.fetchone()[0], 1, "dirty not set after insert")

        # ETL processes the event
        watcher._run_etl(cur)

        # Flag should be cleared
        cur.execute("SELECT dirty FROM change_log WHERE id = 1")
        self.assertEqual(cur.fetchone()[0], 0, "dirty not cleared after ETL")

        # new_data flag should be raised for the chart thread
        self.assertTrue(watcher.new_data)


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    unittest.main(verbosity=2)