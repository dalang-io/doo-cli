"""Exit code constants and custom exceptions for doo-cli."""

# Exit codes
EXIT_SUCCESS = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_AUTH = 3
EXIT_NOT_FOUND = 4
EXIT_TIMEOUT = 5
EXIT_RATE_LIMIT = 6


class CLIError(Exception):
    """Base CLI error with an exit code."""

    def __init__(self, message: str, exit_code: int = EXIT_ERROR) -> None:
        super().__init__(message)
        self.exit_code = exit_code


class AuthError(CLIError):
    """Authentication error."""

    def __init__(self, message: str = "Authentication failed. Run `doo-cli auth login`") -> None:
        super().__init__(message, EXIT_AUTH)


class NotFoundError(CLIError):
    """Resource not found."""

    def __init__(self, message: str) -> None:
        super().__init__(message, EXIT_NOT_FOUND)


class UsageError(CLIError):
    """Invalid usage / missing required arguments."""

    def __init__(self, message: str) -> None:
        super().__init__(message, EXIT_USAGE)


class TimeoutError(CLIError):
    """Operation timed out while waiting."""

    def __init__(self, message: str) -> None:
        super().__init__(message, EXIT_TIMEOUT)


class RateLimitError(CLIError):
    """API rate limit exceeded."""

    def __init__(self, retry_after: int | None = None) -> None:
        msg = "Rate limit exceeded."
        if retry_after is not None:
            msg += f" Try again in {retry_after}s"
        super().__init__(msg, EXIT_RATE_LIMIT)


class ConnectionError(CLIError):
    """Cannot connect to the API."""

    def __init__(self, url: str) -> None:
        super().__init__(
            f"Cannot connect to API at {url}. Is the platform running?",
            EXIT_ERROR,
        )
