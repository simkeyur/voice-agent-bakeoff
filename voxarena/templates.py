# Predefined benchmarking usecase templates for VoxArena

TEMPLATES = {
    "restaurant": {
        "id": "restaurant",
        "name": "Restaurant Reservation (Saffron Leaf)",
        "description": "Book a table for dinner, check parking details, and verify opening hours at Saffron Leaf.",
        "utterances": [
            {
                "id": "u01",
                "text": "Hi, I'd like to book a table for tomorrow evening.",
                "expect": {"response": "Saffron Leaf"}
            },
            {
                "id": "u02",
                "text": "Sure, for 4 people at 7:30 PM under the name Keyur.",
                "expect": {"response": "Keyur"}
            },
            {
                "id": "u03",
                "text": "Do you have any outdoor seating or parking facilities?",
                "expect": {"response": "parking"}
            },
            {
                "id": "u04",
                "text": "Perfect, and what are your opening hours on weekends?",
                "expect": {"response": "hours"}
            },
            {
                "id": "u05",
                "text": "Thank you, that's all I need. See you tomorrow!",
                "expect": {"response": "See you"}
            }
        ]
    },
    "telecom": {
        "id": "telecom",
        "name": "Telecom Customer Support",
        "description": "Verify account details, inquire about a high bill charge, and change subscription to unlimited.",
        "utterances": [
            {
                "id": "u01",
                "text": "Hello, I received my bill today and it's much higher than usual.",
                "expect": {"response": "bill"}
            },
            {
                "id": "u02",
                "text": "My phone number is 555-0199, and the name is Keyur.",
                "expect": {"response": "verify"}
            },
            {
                "id": "u03",
                "text": "My security code is 4321. There is an extra charge of fifty dollars.",
                "expect": {"response": "charge"}
            },
            {
                "id": "u04",
                "text": "Could you please waive this fee and switch me to an unlimited plan?",
                "expect": {"response": "unlimited"}
            },
            {
                "id": "u05",
                "text": "Great, thank you for sorting this out so quickly.",
                "expect": {"response": "welcome"}
            }
        ]
    },
    "smarthome": {
        "id": "smarthome",
        "name": "Smart Home Automation",
        "description": "Query front door lock status, adjust the thermostat temperature, and turn off light zones.",
        "utterances": [
            {
                "id": "u01",
                "text": "Hi, is the front door currently locked?",
                "expect": {"response": "front door"}
            },
            {
                "id": "u02",
                "text": "Okay, please lock it and set the living room thermostat to 72 degrees.",
                "expect": {"response": "thermostat"}
            },
            {
                "id": "u03",
                "text": "Can you turn off all the lights in the kitchen and garage?",
                "expect": {"response": "lights"}
            },
            {
                "id": "u04",
                "text": "Awesome, thank you, that is all.",
                "expect": {"response": "goodbye"}
            }
        ]
    },
    "finance": {
        "id": "finance",
        "name": "Financial Fund Transfer",
        "description": "Check current checking account balance and initiate a transfer from savings to checking.",
        "utterances": [
            {
                "id": "u01",
                "text": "Hey, what is the current balance of my checking account?",
                "expect": {"response": "balance"}
            },
            {
                "id": "u02",
                "text": "I'd like to transfer two hundred dollars from my savings to checking.",
                "expect": {"response": "transfer"}
            },
            {
                "id": "u03",
                "text": "Yes, please proceed with the transfer.",
                "expect": {"response": "successful"}
            }
        ]
    },
    "dryrun": {
        "id": "dryrun",
        "name": "Dry Run Baseline",
        "description": "Basic greeting, simple fact retrieval, and farewell to check latency and socket health.",
        "utterances": [
            {
                "id": "u01",
                "text": "Hello, can you hear me?",
                "expect": {"response": "hello"}
            },
            {
                "id": "u02",
                "text": "What is the capital of France?",
                "expect": {"response": "Paris"}
            },
            {
                "id": "u03",
                "text": "Perfect, thank you, goodbye.",
                "expect": {"response": "goodbye"}
            }
        ]
    }
}
