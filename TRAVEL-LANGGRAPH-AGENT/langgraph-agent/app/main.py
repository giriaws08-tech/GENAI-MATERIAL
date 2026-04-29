from .graph import graph

def run_travel_planner(payload: dict):
    config = {"configurable": {"thread_id": payload.get("session_id", "default")}}
    return graph.invoke(payload, config)


if __name__ == "__main__":
    # test run locally
    result = run_travel_planner({
        "origin": "Dubai",
        "destination": "Bangalore",
        "travel_date_input": "next Friday",
        "total_budget": 1000,
        "messages": []
    })

    print(result)