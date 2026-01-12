"""
LangGraph agent for surf forecasting orchestration
"""
from langgraph.graph import StateGraph, END
from typing import TypedDict, Any
from agents.tools import (
    get_beach_description,
    get_beach_coordinates,
    get_weather_forecast,
    generate_forecast_summary,
)
import json

class SurfState(TypedDict):
    """State for the surf forecasting agent"""
    beach_name: str
    description: str | None
    coordinates: dict[str, float] | None
    weather_data: dict[str, Any] | None
    forecast: str | None

def node_get_description(state: SurfState) -> SurfState:
    """Get beach description"""
    description = get_beach_description(state["beach_name"])
    state["description"] = description
    return state

def node_get_coordinates(state: SurfState) -> SurfState:
    """Get beach coordinates"""
    coordinates = get_beach_coordinates(state["beach_name"], state.get("description", ""))
    state["coordinates"] = coordinates
    return state

def node_get_weather(state: SurfState) -> SurfState:
    """Fetch weather and swell data"""
    if not state.get("coordinates"):
        return state
    
    weather_data = get_weather_forecast(
        state["coordinates"]["latitude"],
        state["coordinates"]["longitude"]
    )
    state["weather_data"] = weather_data
    return state

def node_generate_forecast(state: SurfState) -> SurfState:
    """Generate daily forecast summary"""
    forecast = generate_forecast_summary(
        state["beach_name"],
        state.get("description", ""),
        state.get("weather_data", {})
    )
    state["forecast"] = forecast
    return state

async def run_surf_forecast_agent(beach_name: str) -> dict[str, Any]:
    """
    Run the complete surf forecasting agent pipeline
    """
    # Create graph
    graph = StateGraph(SurfState)
    
    # Add nodes
    graph.add_node("get_description", node_get_description)
    graph.add_node("get_coordinates", node_get_coordinates)
    graph.add_node("get_weather", node_get_weather)
    graph.add_node("generate_forecast", node_generate_forecast)
    
    # Add edges
    graph.set_entry_point("get_description")
    graph.add_edge("get_description", "get_coordinates")
    graph.add_edge("get_coordinates", "get_weather")
    graph.add_edge("get_weather", "generate_forecast")
    graph.add_edge("generate_forecast", END)
    
    # Compile and run
    compiled_graph = graph.compile()
    
    initial_state = {
        "beach_name": beach_name,
        "description": None,
        "coordinates": None,
        "weather_data": None,
        "forecast": None,
    }
    
    result = compiled_graph.invoke(initial_state)
    
    return {
        "beach_name": result["beach_name"],
        "description": result["description"],
        "coordinates": result["coordinates"],
        "weather_data": result["weather_data"],
        "forecast": result["forecast"],
        "success": result["forecast"] is not None,
    }
