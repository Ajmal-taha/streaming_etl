-- an SQL Query to setup the SalesDB database 
-- and create the orders table with some initial data for testing purposes.

CREATE DATABASE SalesDB;
GO

USE SalesDB;
GO

-- creating the orders table:
-- order_id: a unique identifier for each order, set to auto-increment.
-- customer_id: an integer representing the ID of the customer placing the order.
-- amount: a decimal value representing the total amount of the order.
-- order_date: a datetime value representing when the order was placed.
CREATE TABLE orders (
    order_id INT IDENTITY(1,1) PRIMARY KEY,
    customer_id INT NOT NULL,
    amount DECIMAL(10,2) NOT NULL,
    order_date DATETIME DEFAULT GETDATE()
);
GO

-- Optional: seed a few starting orders for testing purposes.
INSERT INTO orders (customer_id, amount) VALUES
(1, 120.50),
(2, 45.00),
(3, 670.25),
(1, 80.00),
(4, 300.00);
GO