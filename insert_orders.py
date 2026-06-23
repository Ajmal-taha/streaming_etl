"""
insert_orders.py
-----------------
Simulates new sales coming into the orders table.
Run this in one terminal while watch_and_visualize.py runs in another.
"""

import pyodbc
import random
import time
import os
from dotenv import load_dotenv

load_dotenv()

# --- SQL SERVER SETUP ---
SERVER = os.environ.get("SERVER")
DATABASE = os.environ.get("DATABASE")
DRIVER = os.environ.get("DRIVER" )

CONN_STR = (
    f"DRIVER={DRIVER};"
    f"SERVER={SERVER};"
    f"DATABASE={DATABASE};"
    f"Trusted_Connection=yes;"
)

CUSTOMER_IDS = list(range(1, 16))   # pretend we have 15 customers


def insert_random_order(cursor):
    """
    inserts a random order into the orders table with a random customer_id and amount
    to simulate new sales coming in. The amount is a random float between $10 and $250.
    """
    customer_id = random.choice(CUSTOMER_IDS)
    amount = round(random.uniform(10, 250), 2)
    cursor.execute(
        "INSERT INTO orders (customer_id, amount) VALUES (?, ?)",
        customer_id, amount
    )
    print(f"Inserted order: customer_id={customer_id}, amount=${amount}")


def main():
    """
    entry point of the script. Connects to the database and 
    continuously inserts random orders every 2-5 seconds until interrupted.
    """
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