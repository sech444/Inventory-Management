#!/usr/bin/env python3
# inventory.py

"""
A minimal “Purchased Inventory” system written in pure Python.

Features
--------
* Add purchases (new SKUs or increase stock of existing ones)
* View current inventory
* Simple report (total value, low‑stock alerts)
* Save / load to JSON file
* Interactive command‑line menu
"""

import json
import os
from dataclasses import dataclass, asdict, field
from typing import Dict, Optional


DATA_FILE = "inventory.json"
LOW_STOCK_THRESHOLD = 5  # items below this quantity will be flagged


@dataclass
class Item:
    """
    Represents a single inventory line‑item.
    """
    sku: str               # Stock Keeping Unit – unique identifier
    name: str              # Human‑readable description
    quantity: int = 0     # Units on hand
    unit_price: float = 0.0  # Average purchase price per unit
    total_cost: float = 0.0  # Cumulative cost (quantity * unit_price)

    def purchase(self, qty: int, price_per_unit: float) -> None:
        """
        Register a new purchase for this item.

        Logic:
        * If the item already has stock, we keep a weighted average for the unit price.
        * total_cost is always increased by qty * price_per_unit.
        """
        if qty <= 0:
            raise ValueError("Purchase quantity must be positive.")
        if price_per_unit < 0:
            raise ValueError("Unit price cannot be negative.")

        # Calculate new weighted average unit price
        new_total_qty = self.quantity + qty
        if new_total_qty == 0:
            # Should never happen (qty > 0) but guard against division by zero
            new_avg_price = 0.0
        else:
            new_avg_price = (
                (self.unit_price * self.quantity) + (price_per_unit * qty)
            ) / new_total_qty

        # Update fields
        self.quantity = new_total_qty
        self.unit_price = round(new_avg_price, 4)  # keep a few decimal places
        self.total_cost = round(self.total_cost + qty * price_per_unit, 2)

    def to_dict(self) -> dict:
        """Return a JSON‑serializable representation."""
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "Item":
        """Re‑create an Item from a dict (produced by to_dict)."""
        return Item(**data)


class Inventory:
    """
    Core inventory container – holds Items indexed by SKU.
    """

    def __init__(self) -> None:
        self._items: Dict[str, Item] = {}

    # --------------------------------------------------------------------- #
    #  Public API
    # --------------------------------------------------------------------- #
    def purchase_item(self, sku: str, name: str, qty: int, price_per_unit: float) -> None:
        """
        Record a purchase. Creates a new Item if the SKU does not exist.
        """
        sku = sku.upper().strip()
        if sku in self._items:
            item = self._items[sku]
            # Update name if you want to keep the most recent naming
            if name:
                item.name = name
        else:
            # New SKU – create a fresh Item
            item = Item(sku=sku, name=name, quantity=0, unit_price=0.0, total_cost=0.0)
            self._items[sku] = item

        # Delegate the arithmetic to the Item instance
        item.purchase(qty, price_per_unit)

    def get_item(self, sku: str) -> Optional[Item]:
        """Return the Item for `sku` or None if not present."""
        return self._items.get(sku.upper().strip())

    def list_inventory(self) -> Dict[str, Item]:
        """Return a copy of the internal dict for read‑only iteration."""
        return dict(self._items)

    def total_inventory_value(self) -> float:
        """Sum of total_cost across all items."""
        return round(sum(item.total_cost for item in self._items.values()), 2)

    def low_stock_items(self) -> Dict[str, Item]:
        """Return items whose quantity is ≤ LOW_STOCK_THRESHOLD."""
        return {sku: it for sku, it in self._items.items() if it.quantity <= LOW_STOCK_THRESHOLD}

    # --------------------------------------------------------------------- #
    #  Persistence helpers
    # --------------------------------------------------------------------- #
    def save_to_file(self, path: str = DATA_FILE) -> None:
        """Serialise the inventory to a JSON file."""
        with open(path, "w", encoding="utf-8") as f:
            json.dump({sku: item.to_dict() for sku, item in self._items.items()}, f, indent=2)
        print(f"✅ Inventory saved to '{path}'")

    def load_from_file(self, path: str = DATA_FILE) -> None:
        """Load inventory from a JSON file (overwrites current state)."""
        if not os.path.exists(path):
            print(f"⚠️  No data file found at '{path}'. Starting with empty inventory.")
            return

        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        self._items = {sku: Item.from_dict(item_dict) for sku, item_dict in raw.items()}
        print(f"✅ Inventory loaded from '{path}' ({len(self._items)} SKUs)")

    # --------------------------------------------------------------------- #
    #  Reporting
    # --------------------------------------------------------------------- #
    def generate_report(self) -> str:
        """
        Produce a multi‑line string showing a table of items,
        the total inventory value, and low‑stock warnings.
        """
        lines = []
        header = f"{'SKU':<10} {'Name':<30} {'Qty':>5} {'Unit $':>9} {'Total $':>10}"
        lines.append(header)
        lines.append("-" * len(header))

        for item in sorted(self._items.values(), key=lambda i: i.sku):
            lines.append(
                f"{item.sku:<10} {item.name[:30]:<30} {item.quantity:>5} "
                f"{item.unit_price:>9.2f} {item.total_cost:>10.2f}"
            )

        lines.append("-" * len(header))
        lines.append(f"TOTAL INVENTORY VALUE: ${self.total_inventory_value():,.2f}")

        low_stock = self.low_stock_items()
        if low_stock:
            lines.append("\n⚠️  Low‑stock items (≤ {} units):".format(LOW_STOCK_THRESHOLD))
            for sku, it in low_stock.items():
                lines.append(f"   - {sku}: {it.name} (Qty: {it.quantity})")
        else:
            lines.append("\nAll items have sufficient stock.")

        return "\n".join(lines)


# ------------------------------------------------------------------------- #
#  CLI – Simple interactive text menu
# ------------------------------------------------------------------------- #
def _print_menu() -> None:
    menu = """
=== Purchased Inventory Menu ===

1. Record a purchase
2. Show inventory report
3. Save inventory to file
4. Load inventory from file
5. List all items (compact view)
6. Exit
"""
    print(menu)


def _prompt_int(prompt: str, min_val: Optional[int] = None) -> int:
    while True:
        try:
            val = int(input(prompt).strip())
            if min_val is not None and val < min_val:
                print(f"❌ Value must be ≥ {min_val}. Try again.")
                continue
            return val
        except ValueError:
            print("❌ Invalid integer. Please try again.")


def _prompt_float(prompt: str, min_val: Optional[float] = None) -> float:
    while True:
        try:
            val = float(input(prompt).strip())
            if min_val is not None and val < min_val:
                print(f"❌ Value must be ≥ {min_val}. Try again.")
                continue
            return val
        except ValueError:
            print("❌ Invalid number. Please try again.")


def main() -> None:
    inv = Inventory()
    # Auto‑load existing file if present
    if os.path.exists(DATA_FILE):
        inv.load_from_file()

    while True:
        _print_menu()
        choice = input("Select an option (1‑6): ").strip()

        if choice == "1":
            print("\n--- Record a Purchase ---")
            sku = input("SKU (unique identifier): ").strip()
            name = input("Item name / description: ").strip()
            qty = _prompt_int("Quantity purchased: ", min_val=1)
            price = _prompt_float("Unit purchase price ($): ", min_val=0.0)
            try:
                inv.purchase_item(sku, name, qty, price)
                print(f"✅ Added {qty} × '{name}' (SKU: {sku.upper()}) at ${price:.2f} each.")
            except ValueError as ve:
                print(f"❌ Error: {ve}")

        elif choice == "2":
            print("\n--- Inventory Report ---")
            print(inv.generate_report())
            print()  # blank line

        elif choice == "3":
            inv.save_to_file()

        elif choice == "4":
            inv.load_from_file()

        elif choice == "5":
            print("\n--- Compact Inventory List ---")
            items = inv.list_inventory()
            if not items:
                print("📦 Inventory is empty.")
            else:
                for sku, it in sorted(items.items()):
                    print(f"{sku}: {it.name} – Qty: {it.quantity}, Unit $: {it.unit_price:.2f}")
            print()

        elif choice == "6":
            print("\n👋 Bye! Remember to save if you made changes.")
            # Optionally prompt to save on exit
            if input("Save before exiting? (y/N): ").strip().lower() == "y":
                inv.save_to_file()
            break

        else:
            print("❓ Invalid selection – please pick a number 1‑6.")


if __name__ == "__main__":
    # Entry point when running `python inventory.py`
    main()
