"""
insert_orders.py
-----------------
Simulates new sales coming into the orders table.
Run this in one terminal while watch_and_visualize.py runs in another.
"""

import pyodbc
import random
import time

# --- EDIT THESE TO MATCH YOUR SQL SERVER SETUP ---
# Matches: Data Source=(localdb)\MSSQLLocalDB;Integrated Security=True;...
SERVER = "(localdb)\\MSSQLLocalDB"
DATABASE = "SalesDB"
DRIVER = "{ODBC Driver 17 for SQL Server}"   # change to 18 if that's what you have

CONN_STR = (
    f"DRIVER={DRIVER};"
    f"SERVER={SERVER};"
    f"DATABASE={DATABASE};"
    f"Trusted_Connection=yes;"
)

CUSTOMER_IDS = list(range(1, 16))   # pretend we have 15 customers


def insert_random_order(cursor):
    customer_id = random.choice(CUSTOMER_IDS)
    amount = round(random.uniform(10, 250), 2)
    cursor.execute(
        "INSERT INTO orders (customer_id, amount) VALUES (?, ?)",
        customer_id, amount
    )
    print(f"Inserted order: customer_id={customer_id}, amount=${amount}")


def main():
    conn = pyodbc.connect(CONN_STR, autocommit=True)
    cursor = conn.cursor()
    print("Connected. Inserting a new random order every 2-5 seconds. Ctrl+C to stop.")
    try:
        while True:
            insert_random_order(cursor)
            time.sleep(random.uniform(2, 5))
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()