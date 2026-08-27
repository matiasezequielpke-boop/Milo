class ToolNotConfiguredError(RuntimeError):
    """Raised when a tool needs a provider that has no key/service configured yet.

    Mirrors app.gateway.ModelNotConfiguredError — same principle across
    every budget-gated integration in this codebase: degrade with a clear
    error, never fake the result.
    """
