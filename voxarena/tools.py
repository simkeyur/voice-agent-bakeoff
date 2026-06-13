import os
import json
from typing import Dict, Any, Optional

# Load data paths relative to this file
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
MENU_PATH = os.path.join(DATA_DIR, "menu.json")
HOURS_PATH = os.path.join(DATA_DIR, "hours.json")

def lookup_menu(category: str) -> str:
    """Retrieve the Saffron Leaf menu items for a specific category (starters, mains, desserts, drinks)."""
    category = category.lower().strip()
    try:
        with open(MENU_PATH, "r") as f:
            menu = json.load(f)
        
        if category in menu:
            items = menu[category]
            res = []
            for it in items:
                res.append(f"- {it['name']} (${it['price']:.2f}): {it['description']}")
            return f"Menu items in '{category}':\n" + "\n".join(res)
        else:
            valid_cats = ", ".join(menu.keys())
            return f"Category '{category}' not found. Please choose one of: {valid_cats}."
    except Exception as e:
        return f"Error retrieving menu: {str(e)}"

def get_hours(day: str) -> str:
    """Retrieve restaurant operating hours for a specific day of the week (e.g. Monday, Tuesday, etc.)."""
    day = day.lower().strip()
    try:
        with open(HOURS_PATH, "r") as f:
            hours = json.load(f)
        
        if day in hours:
            info = hours[day]
            if info["status"] == "closed":
                return f"On {day.capitalize()}, Saffron Leaf is closed."
            else:
                return f"On {day.capitalize()}, Saffron Leaf is open from {info['open_time']} to {info['close_time']}."
        else:
            return f"Day '{day}' not recognized. Please specify a valid day of the week (e.g. Monday, Tuesday)."
    except Exception as e:
        return f"Error retrieving hours: {str(e)}"

def check_reservation_availability(date: str, time: str, party_size: int) -> str:
    """Check table availability for a reservation.
    - date: string (YYYY-MM-DD)
    - time: string (HH:MM or HH:MM AM/PM)
    - party_size: integer
    """
    # Deterministic mock rule for testing constraints:
    # 1. We don't accept parties larger than 12
    # 2. On Friday and Saturday at 7 PM (19:00) for parties >= 6, we are fully booked
    try:
        party_size = int(party_size)
        if party_size <= 0:
            return "Party size must be a positive number."
        if party_size > 12:
            return f"We cannot accommodate parties larger than 12 in our standard dining room. Please call Saffron Leaf directly for private events."

        # Simplistic parsing of time
        # E.g., "19:00", "7:00 PM", etc.
        hour = 0
        cleaned_time = time.upper().strip()
        if "PM" in cleaned_time:
            parts = cleaned_time.replace("PM", "").strip().split(":")
            hour = int(parts[0]) + (12 if int(parts[0]) < 12 else 0)
        elif "AM" in cleaned_time:
            parts = cleaned_time.replace("AM", "").strip().split(":")
            hour = int(parts[0]) if int(parts[0]) < 12 else 0
        else:
            parts = cleaned_time.split(":")
            hour = int(parts[0])
            
        # Simplistic check for weekend
        # Real code would parse date, but we can do a mock check or just check party size
        # If party size is >= 6 and hour is between 18 and 20 (6pm to 8pm), say fully booked
        if party_size >= 6 and 18 <= hour <= 20:
            return f"A table for {party_size} people at {time} on {date} is not available. That peak time is fully booked."
            
        return f"Yes, a table for {party_size} people at {time} on {date} is available at Saffron Leaf. Would you like me to book it?"
    except Exception as e:
        return f"Error checking reservation availability: {str(e)}"

# Shared Tool Definitions
# These are mapped into standard JSON schemas so they can be adapted easily.
TOOL_SCHEMAS = [
    {
        "name": "lookup_menu",
        "description": "Retrieve the Saffron Leaf menu items for a specific category.",
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "The menu category: starters, mains, desserts, or drinks.",
                    "enum": ["starters", "mains", "desserts", "drinks"]
                }
            },
            "required": ["category"]
        }
    },
    {
        "name": "get_hours",
        "description": "Retrieve restaurant operating hours for a specific day of the week.",
        "parameters": {
            "type": "object",
            "properties": {
                "day": {
                    "type": "string",
                    "description": "The day of the week (e.g., Monday, Tuesday, Sunday)."
                }
            },
            "required": ["day"]
        }
    },
    {
        "name": "check_reservation_availability",
        "description": "Check table availability for a reservation on a given date, time, and party size.",
        "parameters": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "The date of reservation in YYYY-MM-DD format."
                },
                "time": {
                    "type": "string",
                    "description": "The time of reservation (e.g. 19:00 or 7:00 PM)."
                },
                "party_size": {
                    "type": "integer",
                    "description": "The number of guests."
                }
            },
            "required": ["date", "time", "party_size"]
        }
    }
]

# Mapping to execute the functions by name
TOOL_FUNCTION_MAP = {
    "lookup_menu": lookup_menu,
    "get_hours": get_hours,
    "check_reservation_availability": check_reservation_availability
}

def execute_tool(name: str, arguments: Dict[str, Any]) -> str:
    """Helper to execute a tool by name with arguments dict."""
    if name not in TOOL_FUNCTION_MAP:
        return f"Tool '{name}' is not a valid tool."
    try:
        return TOOL_FUNCTION_MAP[name](**arguments)
    except TypeError as e:
        return f"Invalid arguments for tool '{name}': {str(e)}"
    except Exception as e:
        return f"Execution error for tool '{name}': {str(e)}"
