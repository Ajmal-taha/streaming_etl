-- Run this once in SSMS to set everything up.
-- If SalesDB already exists from the previous version, start from Step 2.

-- ── STEP 1: Create database ───────────────────────────────────────────────────
CREATE DATABASE SalesDB;
GO

USE SalesDB;
GO

-- ── STEP 2: Orders table ──────────────────────────────────────────────────────
CREATE TABLE orders (
    order_id    INT IDENTITY(1,1) PRIMARY KEY,
    customer_id INT NOT NULL,
    amount      DECIMAL(10,2) NOT NULL,
    order_date  DATETIME DEFAULT GETDATE()
);
GO

-- ── STEP 3: change_log table ──────────────────────────────────────────────────
-- Always a single row. The trigger flips dirty = 1 on every INSERT into orders.
-- Python resets it back to 0 after processing.
CREATE TABLE change_log (
    id           INT PRIMARY KEY DEFAULT 1,   -- always 1 row
    dirty        BIT NOT NULL DEFAULT 0,
    last_updated DATETIME DEFAULT GETDATE()
);
GO

-- Seed the single row
INSERT INTO change_log (id, dirty) VALUES (1, 0);
GO

-- ── STEP 4: Trigger on orders ─────────────────────────────────────────────────
-- Fires automatically after every INSERT. No Python involvement needed.
CREATE TRIGGER trg_orders_after_insert
ON orders
AFTER INSERT
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE change_log
    SET    dirty        = 1,
           last_updated = GETDATE()
    WHERE  id           = 1;
END;
GO

-- ── STEP 5: Seed some starting orders ────────────────────────────────────────
INSERT INTO orders (customer_id, amount) VALUES
(1, 120.50),
(2, 45.00),
(3, 670.25),
(1, 80.00),
(4, 300.00);
GO

-- After the inserts above the trigger will have set dirty = 1.
-- Reset it so Python starts clean.
UPDATE change_log SET dirty = 0 WHERE id = 1;
GO