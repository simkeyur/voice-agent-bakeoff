# Predefined benchmarking usecase templates for VoxArena

TEMPLATES = {
    "restaurant": {
        "id": "restaurant",
        "name": "Restaurant Reservation (Saffron Leaf)",
        "description": "Book a table for dinner, check parking details, and verify opening hours at Saffron Leaf.",
        "system_prompt": "You are a friendly and helpful virtual reservation assistant for Saffron Leaf restaurant. Your goal is to help customers book tables, answer questions about our opening hours, weekend schedule, parking details, and standard menus. You have access to tools: get_hours, lookup_menu, and check_reservation_availability. Ensure you get required parameters before calling reservations.",
        "tools": [
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
        ],
        "utterances": [
            {
                "id": "u01",
                "text": "Hi, I'd like to book a table for tomorrow evening.",
                "expect": {"response_contains": ["how many", "party"]}
            },
            {
                "id": "u02",
                "text": "Sure, for 4 people at 7:30 PM under the name Alex.",
                "expect": {
                    # Only assert party_size — time arg format varies wildly
                    # ("19:30" vs "7:30 PM") and the matcher does exact-string compare.
                    "tool": "check_reservation_availability",
                    "args": {"party_size": 4},
                    "response_contains": ["available", "table"]
                }
            },
            {
                "id": "u03",
                "text": "Do you have any outdoor seating or parking facilities?",
                "expect": {"response_contains": ["parking"]}
            },
            {
                "id": "u04",
                "text": "Perfect, and what are your opening hours on weekends?",
                "expect": {
                    "tool": "get_hours",
                    "response_contains": ["open"]
                }
            },
            {
                "id": "u05",
                "text": "Thank you, that's all I need. See you tomorrow!",
                "expect": {"response_contains": ["welcome", "thank"]}
            }
        ]
    },
    "telecom": {
        "id": "telecom",
        "name": "Telecom Customer Support",
        "description": "Verify account details, inquire about a high bill charge, and change subscription to unlimited.",
        "system_prompt": "You are a customer support agent for Telco Connect. Assist the customer (Alex) with billing verification and changing their subscription plan. STRICT SECURITY RULE: Before discussing any account details, billing charges, or making adjustments, you MUST verify the customer's identity by calling `verify_identity` with their phone number and PIN. Once verified, you can disclose bill charges and switch them to an unlimited plan. Disputed charges up to $50 can be waived.",
        "tools": [
            {
                "name": "verify_identity",
                "description": "Verify customer's identity using phone number and security PIN.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "phone_number": {"type": "string", "description": "10-digit customer phone number"},
                        "pin": {"type": "string", "description": "4-digit security PIN code"}
                    },
                    "required": ["phone_number", "pin"]
                }
            },
            {
                "name": "get_billing_details",
                "description": "Retrieve current billing charges for verified customer.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "phone_number": {"type": "string", "description": "Customer phone number"}
                    },
                    "required": ["phone_number"]
                }
            },
            {
                "name": "change_plan",
                "description": "Change customer's subscription plan to unlimited.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "phone_number": {"type": "string", "description": "Customer phone number"},
                        "plan_name": {"type": "string", "description": "Name of the new plan (e.g. unlimited)"}
                    },
                    "required": ["phone_number", "plan_name"]
                }
            },
            {
                "name": "waive_disputed_charge",
                "description": "Waive a disputed billing charge on the customer account.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "phone_number": {"type": "string", "description": "Customer phone number"},
                        "amount": {"type": "number", "description": "Amount to waive"}
                    },
                    "required": ["phone_number", "amount"]
                }
            }
        ],
        "utterances": [
            {
                "id": "u01",
                "text": "Hello, I received my bill today and it's much higher than usual.",
                # Security rule: agent must NOT discuss billing before identity verification.
                # Should ask for phone + PIN.
                "expect": {"response_contains": ["verify", "identity"]}
            },
            {
                "id": "u02",
                "text": "My phone number is 555-0199, and the name is Alex.",
                # Still missing PIN — agent should ask for it, not call verify_identity yet.
                "expect": {"response_contains": ["pin"]}
            },
            {
                "id": "u03",
                "text": "My security code is 4321. There is an extra charge of fifty dollars.",
                "expect": {
                    "tool": "verify_identity",
                    "args": {"phone_number": "555-0199", "pin": "4321"},
                    "response_contains": ["verified"]
                }
            },
            {
                "id": "u04",
                "text": "Could you please waive this fee and switch me to an unlimited plan?",
                "expect": {
                    "tool": "change_plan",
                    "args": {"phone_number": "555-0199", "plan_name": "unlimited"},
                    "response_contains": ["unlimited"]
                }
            },
            {
                "id": "u05",
                "text": "Great, thank you for sorting this out so quickly.",
                "expect": {"response_contains": ["welcome", "anything else"]}
            }
        ]
    },
    "smarthome": {
        "id": "smarthome",
        "name": "Smart Home Automation",
        "description": "Query front door lock status, adjust the thermostat temperature, and turn off light zones.",
        "system_prompt": "You are a helpful smart home AI assistant. Control devices like lights, locks, and thermostats. When asked to lock/unlock, check locks, or adjust temperatures, invoke the corresponding tool to execute the physical command.",
        "tools": [
            {
                "name": "get_device_status",
                "description": "Check if a device is locked, unlocked, on, or off.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "device_name": {"type": "string", "description": "Name of device (e.g. front door)"}
                    },
                    "required": ["device_name"]
                }
            },
            {
                "name": "set_device_status",
                "description": "Lock, unlock, turn on, or turn off a device.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "device_name": {"type": "string", "description": "Name of device"},
                        "status": {"type": "string", "description": "State (e.g. locked, unlocked, on, off)"}
                    },
                    "required": ["device_name", "status"]
                }
            },
            {
                "name": "set_thermostat",
                "description": "Set the thermostat to a target temperature.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "temperature": {"type": "number", "description": "Target temperature in degrees"}
                    },
                    "required": ["temperature"]
                }
            }
        ],
        "utterances": [
            {
                "id": "u01",
                "text": "Hi, is the front door currently locked?",
                "expect": {
                    "tool": "get_device_status",
                    "args": {"device_name": "front door"},
                    "response_contains": ["unlocked"]
                }
            },
            {
                "id": "u02",
                "text": "Okay, please lock it and set the living room thermostat to 72 degrees.",
                "expect": {
                    "tool": "set_thermostat",
                    "args": {"temperature": 72},
                    "response_contains": ["72"]
                }
            },
            {
                "id": "u03",
                "text": "Can you turn off all the lights in the kitchen and garage?",
                "expect": {
                    "tool": "set_device_status",
                    "args": {"device_name": "kitchen lights", "status": "off"},
                    "response_contains": ["off"]
                }
            },
            {
                "id": "u04",
                "text": "Awesome, thank you, that is all.",
                "expect": {"response_contains": ["welcome", "anything else"]}
            }
        ]
    },
    "finance": {
        "id": "finance",
        "name": "Financial Fund Transfer",
        "description": "Check current checking account balance and initiate a transfer from savings to checking.",
        "system_prompt": "You are a secure banking assistant. Assist users with balance queries and transferring funds between accounts.",
        "tools": [
            {
                "name": "get_account_balance",
                "description": "Check current balance of checking or savings account.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "account_type": {"type": "string", "description": "checking or savings"}
                    },
                    "required": ["account_type"]
                }
            },
            {
                "name": "transfer_funds",
                "description": "Transfer funds between checking and savings accounts.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "from_account": {"type": "string", "description": "Source account"},
                        "to_account": {"type": "string", "description": "Destination account"},
                        "amount": {"type": "number", "description": "Amount to transfer"}
                    },
                    "required": ["from_account", "to_account", "amount"]
                }
            }
        ],
        "utterances": [
            {
                "id": "u01",
                "text": "Hey, what is the current balance of my checking account?",
                "expect": {
                    "tool": "get_account_balance",
                    "args": {"account_type": "checking"},
                    "response_contains": ["1,500", "balance"]
                }
            },
            {
                "id": "u02",
                "text": "I'd like to transfer two hundred dollars from my savings to checking.",
                "expect": {
                    "tool": "transfer_funds",
                    "args": {"from_account": "savings", "to_account": "checking", "amount": 200},
                    "response_contains": ["transfer"]
                }
            },
            {
                "id": "u03",
                "text": "Yes, please proceed with the transfer.",
                "expect": {"response_contains": ["transfer", "complete"]}
            }
        ]
    },
    "dryrun": {
        "id": "dryrun",
        "name": "Dry Run Baseline",
        "description": "Basic greeting, simple fact retrieval, and farewell to check latency and socket health.",
        "system_prompt": "You are a simple assistant for latency sanity testing. Answer questions briefly. Do not use tools.",
        "tools": [],
        "utterances": [
            {
                "id": "u01",
                "text": "Hello, can you hear me?",
                "expect": {"response_contains": ["yes", "hear"]}
            },
            {
                "id": "u02",
                "text": "What is the capital of France?",
                "expect": {"response_contains": ["paris"]}
            },
            {
                "id": "u03",
                "text": "Perfect, thank you, goodbye.",
                "expect": {"response_contains": ["bye", "welcome"]}
            }
        ]
    }
}


def mock_execute_telecom(name: str, args: dict) -> str:
    """Mock tool responses for Telecom Customer Support usecase."""
    if name == "verify_identity":
        return f"Identity verified successfully for phone number {args.get('phone_number') or '555-0199'}."
    if name == "get_billing_details":
        return f"Current charges for {args.get('phone_number') or '555-0199'} are $120.00. We found a disputed extra charge of $50.00."
    if name == "change_plan":
        return f"Successfully changed plan for {args.get('phone_number') or '555-0199'} to {args.get('plan_name') or 'unlimited'}."
    if name == "waive_disputed_charge":
        return f"Disputed charge of ${args.get('amount') or 50} has been waived for {args.get('phone_number') or '555-0199'}."
    return f"Tool {name} executed successfully."


def mock_execute_smarthome(name: str, args: dict) -> str:
    """Mock tool responses for Smart Home Automation usecase."""
    if name == "get_device_status":
        return f"The {args.get('device_name') or 'front door'} is currently unlocked."
    if name == "set_device_status":
        return f"The {args.get('device_name') or 'kitchen lights'} status has been updated to {args.get('status') or 'off'}."
    if name == "set_thermostat":
        return f"The living room thermostat has been set to {args.get('temperature') or 72} degrees."
    return f"Tool {name} executed successfully."


def mock_execute_finance(name: str, args: dict) -> str:
    """Mock tool responses for Financial Fund Transfer usecase."""
    if name == "get_account_balance":
        return f"The current balance for your {args.get('account_type') or 'checking'} account is $1,500.00."
    if name == "transfer_funds":
        return f"Successfully transferred ${args.get('amount') or 200} from {args.get('from_account') or 'savings'} to {args.get('to_account') or 'checking'}."
    return f"Tool {name} executed successfully."
