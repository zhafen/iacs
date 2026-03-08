import pandas as pd

component_tables = {
    "users": pd.DataFrame(
        [
            {"user_id": 1, "name": "Alice Johnson", "email": "alice@example.com", "created_at": "2023-01-15"},
            {"user_id": 2, "name": "Bob Smith", "email": "bob@example.com", "created_at": "2023-02-20"},
            {"user_id": 3, "name": "Carol White", "email": "carol@example.com", "created_at": "2023-03-05"},
        ]
    ),
    "orders": pd.DataFrame(
        [
            {"order_id": 101, "user_id": 1, "product_id": 42, "quantity": 2, "ordered_at": "2023-04-01"},
            {"order_id": 102, "user_id": 2, "product_id": 17, "quantity": 1, "ordered_at": "2023-04-03"},
            {"order_id": 103, "user_id": 1, "product_id": 17, "quantity": 3, "ordered_at": "2023-04-07"},
            {"order_id": 104, "user_id": 3, "product_id": 42, "quantity": 1, "ordered_at": "2023-04-10"},
        ]
    ),
    "products": pd.DataFrame(
        [
            {"product_id": 17, "name": "Widget A", "category": "hardware", "price_usd": 9.99},
            {"product_id": 42, "name": "Widget B", "category": "hardware", "price_usd": 24.99},
            {"product_id": 88, "name": "Service Plan", "category": "service", "price_usd": 49.99},
        ]
    ),
}
