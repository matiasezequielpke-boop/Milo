"""Milo + Warden on Claude: the live agent loop behind the chat.

- prompts.py  — the stable system prompt (who Milo and Warden are, the rules)
- tools.py    — what the model can call; money tools only *propose*
- history.py  — rebuilds the exact Messages API history from the DB
- runner.py   — the streaming tool-use loop that the chat SSE endpoint drives
"""
