import sys
sys.path.insert(0, "chatbot/backend")
from app.conversations import ConversationStore


def test_context_is_scoped_to_app_principal_and_conversation():
    store = ConversationStore()
    entry = store.get("shop", "alice", "chat-1")
    entry.turns.append({"content": "private"})
    assert store.get("shop", "alice", "chat-1") is entry
    assert not store.get("shop", "bob", "chat-1").turns
    assert not store.get("his", "alice", "chat-1").turns
    assert not store.get("shop", "alice", "chat-2").turns


def test_context_expires_and_capacity_is_bounded():
    store = ConversationStore(capacity=2, ttl=30)
    entry = store.get("shop", "a", "1")
    entry.updated -= 31
    assert store.get("shop", "a", "1") is not entry
    store.get("shop", "a", "2")
    store.get("shop", "a", "3")
    assert len(store.entries) == 2
