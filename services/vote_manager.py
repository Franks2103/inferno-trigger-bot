import math


class VoteManager:
    """Generic vote tracker for any action (skip, etc.)."""

    def __init__(self, threshold: float = 0.5, min_votes: int = 1):
        self._threshold = threshold
        self._min_votes = min_votes
        self._votes: set[int] = set()

    def reset(self) -> None:
        self._votes.clear()

    def has_voted(self, user_id: int) -> bool:
        return user_id in self._votes

    def add(self, user_id: int, total_listeners: int) -> tuple[int, int, bool]:
        """
        Add a vote. Returns (current_votes, required_votes, passed).
        total_listeners = number of non-bot members in VC.
        """
        self._votes.add(user_id)
        required = max(self._min_votes, math.ceil(total_listeners * self._threshold))
        return len(self._votes), required, len(self._votes) >= required
