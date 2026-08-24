import os
import json

PRODUCTS_FILE = "data/products.json"

def load_products():
    if not os.path.exists(PRODUCTS_FILE):
        return []
    with open(PRODUCTS_FILE) as f:
        return json.load(f)
        

def save_products(products):
    with open(PRODUCTS_FILE, "w") as f:
        json.dump(products, f, indent=2)

        # --- temporary test (delete in Step 5) ---
test = [{"id": 1, "name": "Test Item", "cost": 10, "price": 25, "quantity": 3}]
save_products(test)
print(load_products())