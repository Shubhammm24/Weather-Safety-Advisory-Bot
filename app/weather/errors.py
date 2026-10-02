"""Custom exceptions for the weather client."""


class WeatherUnavailable(Exception):
    """Raised when the weather API is unreachable, times out, or returns non-200."""

    def __init__(self, message: str = "Weather service is currently unavailable."):
        self.message = message
        super().__init__(self.message)


class LocationNotFound(Exception):
    """Raised when geocoding returns no results for the given location name."""

    def __init__(self, location: str):
        self.location = location
        self.message = f"Could not find a location matching '{location}'."
        super().__init__(self.message)
