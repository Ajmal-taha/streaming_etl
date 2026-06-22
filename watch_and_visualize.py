"""
Polls the orders table for new rows, recalculates customer spend
categories, and keeps a live bar chart updated.

ETL steps happen inside update():
  Extract  -> fetch_new_orders()
  Transform-> get_category_counts()
  Load     -> redraw the chart
"""

import pyodbc
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.animation as animation

# --- SQL SERVER SETUP ---
SERVER = "(localdb)\\MSSQLLocalDB"
DATABASE = "SalesDB"
DRIVER = "{ODBC Driver 17 for SQL Server}"

CONN_STR = (
    f"DRIVER={DRIVER};"
    f"SERVER={SERVER};"
    f"DATABASE={DATABASE};"
    f"Trusted_Connection=yes;"
)

POLL_INTERVAL_MS = 3000  # how often to check the DB, in milliseconds

# Spend thresholds for categorization
"""
customers having spend >= $500 are "High"
customers having spend >= $200 but < $500 are "Medium"
customers having spend < $200 are "Low"
"""
HIGH_THRESHOLD = 500
MEDIUM_THRESHOLD = 200


def categorize(total_spend):
    if total_spend >= HIGH_THRESHOLD:
        return "High"
    elif total_spend >= MEDIUM_THRESHOLD:
        return "Medium"
    else:
        return "Low"


class OrderWatcher:
    def __init__(self, conn_str):
        self.conn = pyodbc.connect(conn_str)
        self.last_seen_id = 0
        self.orders = pd.DataFrame(columns=["order_id", "customer_id", "amount"])
        self._load_existing_orders()

    def _load_existing_orders(self):
        """Load whatever is already in the table when the script starts."""
        df = pd.read_sql(
            "SELECT order_id, customer_id, amount FROM orders ORDER BY order_id",
            self.conn
        )
        if not df.empty:
            self.orders = df
            self.last_seen_id = int(df["order_id"].max())
        print(f"Loaded {len(self.orders)} existing orders. Starting watch...")

    def fetch_new_orders(self):
        """Extract step: pull only rows inserted since the last check."""
        query = (
            "SELECT order_id, customer_id, amount FROM orders "
            "WHERE order_id > ? ORDER BY order_id"
        )
        new_rows = pd.read_sql(query, self.conn, params=[self.last_seen_id])
        if not new_rows.empty:
            self.orders = pd.concat([self.orders, new_rows], ignore_index=True)
            self.last_seen_id = int(new_rows["order_id"].max())
        return new_rows

    def get_category_counts(self):
        """Transform step: total spend per customer -> category counts."""
        if self.orders.empty:
            return pd.Series(dtype=int)
        spend_per_customer = self.orders.groupby("customer_id")["amount"].sum()
        categories = spend_per_customer.apply(categorize)
        counts = categories.value_counts().reindex(["Low", "Medium", "High"]).fillna(0)
        return counts


def main():
    watcher = OrderWatcher(CONN_STR)

    fig, ax = plt.subplots(figsize=(6, 5))
    colors = {"Low": "#9CA3AF", "Medium": "#3B82F6", "High": "#16A34A"}

    def update(frame):
        new_rows = watcher.fetch_new_orders()      # Extract
        counts = watcher.get_category_counts()      # Transform

        ax.clear()                                  # Load (redraw)
        bars = ax.bar(counts.index, counts.values,
                       color=[colors[c] for c in counts.index])
        ax.set_title("Customer Spend Categories (live)")
        ax.set_ylabel("Number of customers")
        top = counts.values.max() if len(counts) else 1
        ax.set_ylim(0, top + 2)

        for bar, value in zip(bars, counts.values):
            ax.text(bar.get_x() + bar.get_width() / 2, value + 0.1,
                     int(value), ha="center")

        if not new_rows.empty:
            print(f"[update] {len(new_rows)} new order(s) processed. "
                  f"Totals -> {dict(counts)}")

    ani = animation.FuncAnimation(fig, update, interval=POLL_INTERVAL_MS)
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()