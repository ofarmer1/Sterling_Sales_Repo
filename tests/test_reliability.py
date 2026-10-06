"""Tests for AI error messages, incomplete answers and the spending cap."""

from types import SimpleNamespace

import httpx2
import openai
import pytest

from ai_client import AIClient, AIError, explain_error
from batch import process_batch, research_one
from leads_store import BudgetExceeded, add_companies, get_lead, log_usage
from ai_client import Usage
from settings_store import DEFAULT_SETTINGS
from tests.fake_ai import standard_fake_ai
from tests.fake_database import FakeDatabase

REQUEST = httpx2.Request("POST", "https://api.openai.com/v1/responses")


def status_error(kind, status, message="error"):
    response = httpx2.Response(status, request=REQUEST)
    return kind(message, response=response, body=None)


def test_error_messages_say_what_to_do():
    assert "API key" in explain_error(status_error(openai.AuthenticationError, 401))
    assert "out of credits" in explain_error(
        status_error(openai.RateLimitError, 429, "You exceeded your current quota"))
    assert "busy" in explain_error(status_error(openai.RateLimitError, 429, "slow down"))
    assert "Couldn't reach OpenAI" in explain_error(openai.APIConnectionError(request=REQUEST))
    assert "too long" in explain_error(openai.APITimeoutError(request=REQUEST))
    assert "model name" in explain_error(status_error(openai.NotFoundError, 404))
    assert "their side" in explain_error(status_error(openai.InternalServerError, 500))


def fake_client(response=None, error=None):
    """An AIClient whose OpenAI connection is replaced by a stub."""
    client = AIClient("sk-test-not-real")

    def create(**kwargs):
        if error:
            raise error
        return response

    client.client = SimpleNamespace(responses=SimpleNamespace(create=create))
    return client


def test_api_errors_become_plain_ai_errors():
    client = fake_client(error=status_error(openai.AuthenticationError, 401))
    with pytest.raises(AIError, match="API key"):
        client.ask_json("i", "p", {}, "s")


def test_incomplete_answer_is_an_error():
    response = SimpleNamespace(status="incomplete", incomplete_details=SimpleNamespace(reason="max_output_tokens"))
    with pytest.raises(AIError, match="stopped before finishing"):
        fake_client(response).ask_json("i", "p", {}, "s")


def test_bad_json_is_an_error():
    response = SimpleNamespace(status="completed", output_text="not json", output=[], usage=None)
    with pytest.raises(AIError, match="expected format"):
        fake_client(response).ask_json("i", "p", {}, "s")


def test_client_retries_and_times_out():
    client = AIClient("sk-test-not-real")
    assert client.client.max_retries == 3
    assert client.budget_usd == 25.00


def spend(db, dollars):
    # 1 web search = $0.01, so this logs `dollars` worth of usage.
    log_usage(db, "research", Usage(model="gpt-5.4-mini", web_searches=int(dollars * 100)))


def test_budget_stops_research_before_calling_ai():
    db = FakeDatabase()
    added, _ = add_companies(db, [{"name": "Acme"}])
    ai = standard_fake_ai()
    ai.budget_usd = 1.00
    spend(db, 1.00)
    with pytest.raises(BudgetExceeded):
        research_one(db, ai, DEFAULT_SETTINGS, added[0]["id"])
    assert ai.calls == []
    assert get_lead(db, added[0]["id"])["status"] == "new"  # not marked failed


def test_budget_stops_the_whole_batch():
    db = FakeDatabase()
    added, _ = add_companies(db, [{"name": "A"}, {"name": "B"}, {"name": "C"}])
    ai = standard_fake_ai()
    ai.budget_usd = 1.00
    spend(db, 1.00)
    summary = process_batch(db, ai, DEFAULT_SETTINGS, [r["id"] for r in added])
    assert len(summary["failed"]) == 1
    assert "budget" in summary["failed"][0][1]
    assert ai.calls == []


def test_under_budget_runs_normally():
    db = FakeDatabase()
    added, _ = add_companies(db, [{"name": "A"}])
    ai = standard_fake_ai()
    ai.budget_usd = 1.00
    spend(db, 0.50)
    research_one(db, ai, DEFAULT_SETTINGS, added[0]["id"])
    assert len(ai.calls) == 1
