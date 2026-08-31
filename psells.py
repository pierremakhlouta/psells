import os
import json

INVENTORY_FILE = "data/inventory.json"
SALES_FILE = "data/sales.json"
RETURNS_FILE = "data/returns.json"
PAYMENTS_FILE = "data/payments.json"

def load_data(filepath):
    if not os.path.exists(filepath):
        return []
    with open(filepath) as f:
        return json.load(f)
        

def save_data(data, filepath):
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)

def next_id(records):
    if not records:
        return 1
    return max(record["id"] for record in records) + 1


def view_dashboard():
    pass  

def view_inventory():
    pass  

def search():
    pass  

def add():
    pass  

def edit():
    pass  

def delete():
    pass  

def record_sale():
    pass  

def record_return():
    pass

def record_payment():
    pass

while True:
    choice = input("Choose an option!\n0: Quit\n1: View Dashboard\n2: View Inventory\n3: Search\n4: Add\n5: Edit\n6: Delete\n7: Record Sale\n8: Record Return\n9: Record Payment\n")
    if choice == "0":
        break
    elif choice == "1":
        view_dashboard()
    elif choice == "2":
        view_inventory()
    elif choice == "3":
        search()
    elif choice == "4":
        add()
    elif choice == "5":
        edit()
    elif choice == "6":
        delete()
    elif choice == "7":
        record_sale()
    elif choice == "8":
        record_return()
    elif choice == "9":
        record_payment()
    else:
        print("Invalid input try again!\n")