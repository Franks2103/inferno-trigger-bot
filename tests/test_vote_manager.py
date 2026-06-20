import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from services.vote_manager import VoteManager


def test_single_vote_passes_when_only_listener():
    vm = VoteManager(threshold=0.5, min_votes=1)
    votes, required, passed = vm.add(user_id=1, total_listeners=1)
    assert passed is True
    assert votes == 1
    assert required == 1


def test_needs_majority_of_two():
    vm = VoteManager(threshold=0.5, min_votes=1)
    votes, required, passed = vm.add(user_id=1, total_listeners=4)
    assert passed is False
    assert required == 2

    votes, required, passed = vm.add(user_id=2, total_listeners=4)
    assert passed is True


def test_reset_clears_votes():
    vm = VoteManager(threshold=0.5, min_votes=1)
    vm.add(user_id=1, total_listeners=2)
    vm.reset()
    assert not vm.has_voted(1)


def test_duplicate_vote_counts_once():
    vm = VoteManager(threshold=0.5, min_votes=1)
    vm.add(user_id=1, total_listeners=4)
    votes, _, _ = vm.add(user_id=1, total_listeners=4)
    assert votes == 1
