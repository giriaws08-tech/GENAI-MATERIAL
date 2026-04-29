# app/nodes.py

import os
import json
import re
import requests
from typing import List, Annotated
import operator

from langchain_openai import ChatOpenAI
from langchain_community.utilities import SerpAPIWrapper

from .state import TravelState

# --- CONFIG ---
llm = ChatOpenAI(model="gpt-4o", temperature=0)
search_tool = SerpAPIWrapper()

DUFFEL_ACCESS_TOKEN = os.getenv("DUFFEL_ACCESS_TOKEN")

# ================================
# INPUT PROCESSOR
# ================================
def input_processor_node(state: TravelState):
    print(f"--- 🔍 PROCESSING: {state['origin']} to {state['destination']} ---")

    prompt = f"""
    Current Date: 2026-04-29
    Convert travel details into strict JSON.

    Origin: {state['origin']}
    Destination: {state['destination']}
    Date: {state['travel_date_input']}

    Format:
    {{
      "origin_iata": "CODE",
      "destination_iata": "CODE",
      "formatted_date": "YYYY-MM-DD"
    }}
    """

    raw_res = llm.invoke(prompt).content.strip()

    clean_json = re.sub(r'^```json\s*|```$', '', raw_res, flags=re.MULTILINE).strip()
    clean_json = clean_json.replace('`', '')

    try:
        data = json.loads(clean_json)
    except Exception:
        print("❌ JSON parsing failed")
        return {}

    return {
        "origin_iata": data["origin_iata"].upper(),
        "destination_iata": data["destination_iata"].upper(),
        "travel_date_formatted": data["formatted_date"]
    }

# ================================
# FLIGHT AGENT
# ================================
def flight_agent(state: TravelState):
    print(f"--- ✈️ FLIGHT SEARCH ---")

    url = "https://api.duffel.com/air/offer_requests?return_offers=true"

    headers = {
        "Duffel-Version": "v2",
        "Authorization": f"Bearer {DUFFEL_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    data = {
        "data": {
            "slices": [
                {
                    "origin": state['origin_iata'],
                    "destination": state['destination_iata'],
                    "departure_date": state['travel_date_formatted']
                }
            ],
            "passengers": [{"type": "adult"}],
            "cabin_class": "economy"
        }
    }

    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()

        res = response.json()
        offers = []

        for offer in res.get("data", {}).get("offers", [])[:3]:
            offers.append({
                "id": offer["id"],
                "airline": offer["owner"]["name"],
                "price": float(offer["total_amount"]),
                "info": f"{offer['owner']['name']} - {offer['total_amount']}"
            })

        return {"flight_options": offers}

    except Exception as e:
        print(f"❌ Flight API error: {e}")
        return {"flight_options": []}

# ================================
# HOTEL AGENT
# ================================
def hotel_agent(state: TravelState):
    print(f"--- 🏨 HOTEL SEARCH ---")

    query = f"best hotels in {state['destination']}"
    res = search_tool.run(query)

    return {
        "hotel_options": [{"info": str(res)[:500]}]
    }

# ================================
# ACTIVITY AGENT
# ================================
def activity_agent(state: TravelState):
    print(f"--- 🎭 ACTIVITIES ---")

    query = f"top attractions in {state['destination']}"
    res = search_tool.run(query)

    return {"activities": [res]}

# ================================
# SUPERVISOR
# ================================
def supervisor_node(state: TravelState):
    total = state.get("total_budget", 0)
    f_price = state.get("selected_flight_price", 0) or 0
    h_price = state.get("selected_hotel_price", 0) or 0

    remaining = total - (f_price + h_price)

    print(f"🧠 Budget left: {remaining}")

    return {"remaining_budget": remaining}

# ================================
# WARNING
# ================================
def budget_warning_node(state: TravelState):
    deficit = abs(state['remaining_budget'])
    return {
        "messages": [{"role": "system", "content": f"Budget exceeded by {deficit}"}]
    }

# ================================
# ROUTER
# ================================
def should_continue(state: TravelState):
    return "warn" if state["remaining_budget"] < 0 else "continue"