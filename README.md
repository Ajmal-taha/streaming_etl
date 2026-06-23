# Streaming ETL Pipeline — SQL Server → Live Chart

An event-driven Python ETL pipeline that reacts to new orders in an MS-SQL (LocalDB) database and updates a live matplotlib bar chart categorizing customers as **High**, **Medium**, or **Low** spenders in real time.

---

## Screenshot

![Live Visualization](images/screenshot.png)

---

## How It Works

```
insert_orders.py                   watch_and_visualize.py
─────────────────                  ──────────────────────────────────────────────
Inserts a random      ──► orders   AFTER INSERT trigger fires automatically
order every 2–5s           table   → sets change_log.dirty = 1

                                   Background thread checks dirty flag (200ms)
                                   → dirty = 1 detected
                                       → Extract  : fetch only new order rows
                                       → Transform: recalculate spend categories
                                       → Load     : signal chart to redraw
                                       → reset dirty = 0, go back to watching
```

**Why event-driven and not polling:**
The watcher's "nothing happened" path is a single 1-row query (`SELECT dirty FROM change_log`). The full ETL only runs when the SQL trigger has actually fired — no wasted cycles scanning the orders table when there's nothing new.

**Spend thresholds:**
| Category | Total Spend |
|----------|-------------|
| 🟢 High   | ≥ $500      |
| 🔵 Medium | ≥ $200      |
| ⚪ Low    | < $200      |

---

## Setup

**1. Create the database** — run `setup_database.sql` in SSMS. This creates the `orders` table, `change_log` table, and the `AFTER INSERT` trigger.

**2. Install dependencies**
```bash
pip install -r requirements.txt
```

**3. Run the watcher** (opens the live chart)
```bash
python watch_and_visualize.py
```

**4. Run the producer** (starts inserting random orders)
```bash
python insert_orders.py
```

The chart reacts within ~200ms of each insert. No manual refresh needed.

---

## Running Tests

```bash
# All tests
python test.py

# Unit tests only — no DB required
python -m unittest TestCategorize TestTransform -v

# Integration tests only — needs LocalDB running
python -m unittest TestIntegration -v
```

Integration tests auto-skip if the DB is unreachable.

| Suite | What it covers |
|---|---|
| `TestCategorize` | Spend bucketing logic at and around thresholds |
| `TestTransform` | Category counts, multi-order summing, ETL flags, extract filtering |
| `TestIntegration` | DB connection, schema, trigger behaviour, full event cycle |

---

## Requirements

- Python 3.8+
- MS SQL Server LocalDB (`can also be used with non localDB with proper connectors`)
- ODBC Driver 17 for SQL Server

---

## Project Structure

```
├── setup_database.sql       
├── insert_orders.py         
├── watch_and_visualize.py   
├── test.py              
├── requirements.txt
└── images/
```
