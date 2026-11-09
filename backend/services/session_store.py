from typing import Any, Dict, Optional


class SessionStore:
    def __init__(self):
        # Map session_id to session state
        self.sessions: Dict[str, Dict[str, Any]] = {}

    def get_or_create(self, session_id: str) -> Dict[str, Any]:
        if session_id not in self.sessions:
            self.sessions[session_id] = {
                "active_filters" : {},
                "history": [],
            }
        return self.sessions[session_id]
    
    def updated_filters(self, session_id: str, new_filters: Dict[str, Any]) -> Dict[str, Any]:
        session = self.get_or_create(session_id)
        # Update or remove filters (if value is None, remove key)
        for k, v in new_filters.items():
            if v is None:
                session["active_filters"].pop(k, None)
            else:
                session["active_filters"][k] = v
        return session["active_filters"]

    update_filters = updated_filters
    
    def clear_filters(self, session_id: str):
        session = self.get_or_create(session_id)
        session["active_filters"] = {}

session_store = SessionStore()
