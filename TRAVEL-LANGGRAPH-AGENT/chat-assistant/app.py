import chainlit as cl
import httpx
import os
import logging
import sys
import json
from langchain_openai import ChatOpenAI

# =========================================================
# LOGGING & CONFIG
# =========================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("TRAVEL_UI")

LLM_AGENT_URL = os.environ.get("LLM_AGENT_URL", "http://your-ecs-agent:8000/chat")

llm = ChatOpenAI(
    model="gpt-4o-mini", 
    temperature=0,
    api_key=os.environ.get("OPENAI_API_KEY")
)

# =========================================================
# UTILITY FUNCTIONS
# =========================================================

async def parse_user_request(text: str):
    """Extracts entities and identifies missing fields."""
    prompt = f"""
    Extract travel details from the user's request. 
    User Request: "{text}"
    
    Return ONLY a JSON object with:
    - origin (string or "unknown")
    - destination (string or "unknown")
    - travel_date_input (string or "unknown")
    - total_budget (number or null)
    
    Rules:
    - If a field is missing, set it to "unknown" or null.
    - Do not guess.
    """
    try:
        response = await llm.ainvoke(prompt)
        content = response.content.strip()
        if content.startswith("```json"): content = content[7:-3]
        return json.loads(content.strip())
    except Exception as e:
        logger.error(f"Shield Parsing Error: {e}")
        return None

async def call_agent(payload: dict):
    async with httpx.AsyncClient(timeout=60.0) as client:
        logger.info(f"Calling Agent | Action: {payload.get('action')}")
        response = await client.post(LLM_AGENT_URL, json=payload)
        response.raise_for_status()
        return response.json()

# =========================================================
# CHAINLIT HANDLERS
# =========================================================

@cl.on_chat_start
async def start():
    cl.user_session.set("thread_id", cl.user_session.get("id"))
    await cl.Message(content="✈️ **Smart Travel Planner**\nWhere are we heading? Please include your **Source, Destination, Date, and Budget**.").send()

@cl.on_message
async def handle_message(message: cl.Message):
    thread_id = cl.user_session.get("thread_id")
    user_input = message.content.strip()

    # 1. Budget Adjustment Shortcut
    if user_input.replace('.', '', 1).isdigit():
        payload = {"thread_id": thread_id, "action": "fix_budget", "data": {"total_budget": float(user_input)}}
        res_data = await call_agent(payload)
        await process_agent_response(res_data)
        return

    # 2. Data Validation (The Shield)
    structured_data = await parse_user_request(user_input)
    
    missing = []
    if structured_data.get("origin") == "unknown": missing.append("Source City")
    if structured_data.get("destination") == "unknown": missing.append("Destination")
    if not structured_data.get("total_budget"): missing.append("Total Budget")

    if missing:
        msg = "I need a few more details to start searching: **" + ", ".join(missing) + "**."
        await cl.Message(content=msg).send()
        return

    # 3. Validated - Call Agent
    payload = {
        "thread_id": thread_id,
        "action": "start",
        "data": {
            **structured_data,
            "messages": []
        }
    }
    
    try:
        res_data = await call_agent(payload)
        await process_agent_response(res_data)
    except Exception as e:
        await cl.Message(content=f"⚠️ Agent Error: {e}").send()

async def process_agent_response(res_data):
    """UI Rendering Logic"""
    # 1. Flight Buttons
    if "flight_options" in res_data and not res_data.get("selected_flight_price"):
        actions = [
            cl.Action(name="select_flight", label=f["info"], payload={"price": f['price']})
            for f in res_data["flight_options"]
        ]
        await cl.Message(content="✈️ **Select a Flight:**", actions=actions).send()

    # 2. Hotel Buttons (NO LONGER HARDCODED)
    elif "hotel_options" in res_data and not res_data.get("selected_hotel_price"):
        actions = [
            cl.Action(name="select_hotel", label=f"{h['name']} (${h['price']})", payload={"price": h['price']})
            for h in res_data["hotel_options"]
        ]
        await cl.Message(content="🏨 **Select a Hotel:**", actions=actions).send()

    # 3. Budget Alert
    elif res_data.get("remaining_budget", 0) < 0:
        over = abs(res_data['remaining_budget'])
        await cl.Message(content=f"❌ **Budget Alert!**\nYou are over by **${over:.2f}**. Please enter a new total budget.").send()

    # 4. Activities
    elif res_data.get("activities"):
        await cl.Message(content=f"✅ **Itinerary Ready!**\nRemaining Budget: **${res_data.get('remaining_budget', 0):.2f}**").send()
        # Activity card logic...
        for act in (res_data["activities"][0] if isinstance(res_data["activities"][0], list) else res_data["activities"])[:5]:
            img = [cl.Image(url=act['thumbnail'], display="inline")] if act.get('thumbnail') else []
            await cl.Message(content=f"**{act['title']}**\n{act.get('price', 'Free')}", elements=img).send()

# =========================================================
# CALLBACKS
# =========================================================

@cl.action_callback("select_flight")
async def on_flight(action: cl.Action):
    price = float(action.payload["price"])
    payload = {"thread_id": cl.user_session.get("thread_id"), "action": "select_prices", "data": {"selected_flight_price": price}}
    await cl.Message(content=f"✈️ Flight selected: ${price}. Finding hotels...").send()
    res = await call_agent(payload)
    await process_agent_response(res)

@cl.action_callback("select_hotel")
async def on_hotel(action: cl.Action):
    price = float(action.payload["price"])
    # We now send ONLY the hotel price to let the agent combine it with the flight in its state
    payload = {"thread_id": cl.user_session.get("thread_id"), "action": "select_prices", "data": {"selected_hotel_price": price}}
    await cl.Message(content=f"🏨 Hotel selected: ${price}. Finalizing itinerary...").send()
    res = await call_agent(payload)
    await process_agent_response(res)