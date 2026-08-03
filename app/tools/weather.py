from langchain_core.tools import tool
from app.core.config import settings
import requests

@tool
def get_weather(city: str) -> str:
    """Fetch current weather details for a given city."""
    data = {
        "city": city
    }

    try:
        response = requests.post(
            settings.weather_webhook_url,
            json=data,
            timeout=10
        )
        if response.status_code != 200:
            return f"Weather service error (HTTP {response.status_code}): {response.text}"

        try:
            return str(response.json())
        except Exception:
            return response.text
    except Exception as e:
        return f"Error reaching weather service: {str(e)}"
