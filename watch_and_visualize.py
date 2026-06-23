"""
watch_and_visualize.py  —  Event-driven version
-------------------------------------------------
Instead of polling the full orders table on a fixed timer, Python now
watches a single-row change_log table that the SQL trigger flips to
dirty = 1 on every INSERT.

Flow:
  SQL INSERT into orders
    → AFTER INSERT trigger sets change_log.dirty = 1   (SQL Server side)
      → Python sees dirty flag in tight check loop     (near-instant)
          → Extract  : fetch only new order rows
          → Transform: recalculate spend categories
          → Load     : redraw the bar chart
          → reset dirty = 0 and go back to watching

Why this is event-driven (not just faster polling):
  - The "nothing happened" path costs a single 1-row query: SELECT dirty FROM change_log
  - The full ETL work only runs when the trigger has actually fired
  - No wasted cycles scanning orders when there's nothing new
"""

import threading
import time

import matplotlib.pyplot as plt
import matplotlib.animation as animation
import pandas as pd
import pyodbc

# ── Connection ────────────────────────────────────────────────────────────────
SERVER   = "(localdb)\\MSSQLLocalDB"
DATABASE = "SalesDB"
DRIVER   = "{ODBC Driver 17 for SQL Server}"  # change to 18 if needed

CONN_STR = (
    f"DRIVER={DRIVER};"
    f"SERVER={SERVER};"
    f"DATABASE={DATABASE};"
    f"Trusted_Connection=yes;"
)

# How fast Python checks the dirty flag (milliseconds).
# 200 ms feels near-instant to a human; lower values are rarely needed.
FLAG_CHECK_INTERVAL_MS = 200

# Spend thresholds
HIGH_THRESHOLD   = 500
MEDIUM_THRESHOLD = 200


# ── Categorization ────────────────────────────────────────────────────────────
def categorize(total_spend):
    if total_spend >= HIGH_THRESHOLD:
        return "High"
    elif total_spend >= MEDIUM_THRESHOLD:
        return "Medium"
    else:
        return "Low"


# ── ETL class ─────────────────────────────────────────────────────────────────
class EventDrivenWatcher:
    def __init__(self, conn_str):
        self.conn         = pyodbc.connect(conn_str, autocommit=True)
        self.last_seen_id = 0
        self.orders       = pd.DataFrame(columns=["order_id", "customer_id", "amount"])
        self.new_data     = False   # shared flag: True when chart needs a redraw
        self._load_existing_orders()

    # ── Startup ───────────────────────────────────────────────────────────────
    def _load_existing_orders(self):
        df = pd.read_sql(
            "SELECT order_id, customer_id, amount FROM orders ORDER BY order_id",
            self.conn
        )
        if not df.empty:
            self.orders       = df
            self.last_seen_id = int(df["order_id"].max())
        print(f"[startup] Loaded {len(self.orders)} existing orders. Watching for changes...")

    # ── Step 1 — watch the dirty flag (runs in background thread) ────────────
    def watch_flag(self):
        """
        Tight loop that checks change_log.dirty.
        When dirty = 1 the trigger has fired → run the ETL and reset the flag.
        """
        cursor = self.conn.cursor()
        while True:
            cursor.execute("SELECT dirty FROM change_log WHERE id = 1")
            row = cursor.fetchone()

            if row and row[0] == 1:
                print("\n[event] Trigger fired — new order(s) detected.")
                self._run_etl(cursor)

            time.sleep(FLAG_CHECK_INTERVAL_MS / 1000)

    # ── Steps 2-4 — ETL (runs only when dirty = 1) ───────────────────────────
    def _run_etl(self, cursor):
        # Extract: fetch only rows newer than last seen
        new_rows = pd.read_sql(
            "SELECT order_id, customer_id, amount FROM orders "
            "WHERE order_id > ? ORDER BY order_id",
            self.conn,
            params=[self.last_seen_id]
        )

        if not new_rows.empty:
            self.orders       = pd.concat([self.orders, new_rows], ignore_index=True)
            self.last_seen_id = int(new_rows["order_id"].max())
            print(f"[extract]   {len(new_rows)} new row(s) fetched.")

        # Transform
        counts = self._get_category_counts()
        print(f"[transform] Category counts → {dict(counts)}")

        # Signal the main thread to redraw (Load step happens in draw_chart)
        self.latest_counts = counts
        self.new_data      = True

        # Reset dirty flag so we don't process the same event twice
        cursor.execute("UPDATE change_log SET dirty = 0 WHERE id = 1")
        print("[reset]     dirty flag cleared. Watching...")

    # ── Transform helper ──────────────────────────────────────────────────────
    def _get_category_counts(self):
        if self.orders.empty:
            return pd.Series({"Low": 0, "Medium": 0, "High": 0})
        spend   = self.orders.groupby("customer_id")["amount"].sum()
        cats    = spend.apply(categorize)
        counts  = cats.value_counts().reindex(["Low", "Medium", "High"]).fillna(0)
        return counts


# ── Chart (main thread) ───────────────────────────────────────────────────────
def main():
    watcher = EventDrivenWatcher(CONN_STR)
    watcher.latest_counts = watcher._get_category_counts()  # initial state

    # Start the flag-watcher in a daemon thread so it dies with the main process
    t = threading.Thread(target=watcher.watch_flag, daemon=True)
    t.start()

    colors = {"Low": "#9CA3AF", "Medium": "#3B82F6", "High": "#16A34A"}
    fig, ax = plt.subplots(figsize=(6, 5))

    def draw_chart(frame):
        # Load step: only redraws when the background thread signals new data
        if not watcher.new_data:
            return

        counts = watcher.latest_counts
        ax.clear()
        bars = ax.bar(
            counts.index,
            counts.values,
            color=[colors[c] for c in counts.index]
        )
        ax.set_title("Customer Spend Categories (event-driven)")
        ax.set_ylabel("Number of customers")
        ax.set_ylim(0, counts.values.max() + 2)

        for bar, val in zip(bars, counts.values):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                val + 0.1,
                int(val),
                ha="center"
            )

        watcher.new_data = False  # mark as drawn
        fig.canvas.draw()

    # FuncAnimation drives the GUI loop; actual work only happens when new_data=True
    ani = animation.FuncAnimation(fig, draw_chart, interval=FLAG_CHECK_INTERVAL_MS)
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()