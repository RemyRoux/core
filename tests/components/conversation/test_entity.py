"""Tests for conversation entity."""

from unittest.mock import patch

from homeassistant.components import conversation
from homeassistant.components.conversation.entity import ConversationEntity
from homeassistant.core import Context, HomeAssistant, State
from homeassistant.helpers import chat_session, intent, llm
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util

from tests.common import mock_restore_cache


async def test_state_set_and_restore(hass: HomeAssistant) -> None:
    """Test we set and restore state in the integration."""
    entity_id = "conversation.home_assistant"
    timestamp = "2023-01-01T23:59:59+00:00"
    mock_restore_cache(hass, (State(entity_id, timestamp),))

    await async_setup_component(hass, "homeassistant", {})
    await async_setup_component(hass, "conversation", {})

    state = hass.states.get(entity_id)
    assert state
    assert state.state == timestamp

    now = dt_util.utcnow()
    context = Context()

    with (
        patch(
            "homeassistant.components.conversation.default_agent.DefaultAgent.async_process"
        ) as mock_process,
        patch("homeassistant.util.dt.utcnow", return_value=now),
    ):
        intent_response = intent.IntentResponse(language="en")
        intent_response.async_set_speech("response text")
        mock_process.return_value = conversation.ConversationResult(
            response=intent_response,
        )
        await hass.services.async_call(
            "conversation",
            "process",
            {"text": "Hello"},
            context=context,
            blocking=True,
        )

    assert len(mock_process.mock_calls) == 1

    state = hass.states.get(entity_id)
    assert state
    assert state.state == now.isoformat()
    assert state.context is context


class TestEntity(ConversationEntity):
    """Test conversation entity."""

    @property
    def supported_languages(self) -> list[str]:
        """Return supported languages."""
        return ["en"]

    async def _async_handle_message(
        self,
        user_input: conversation.ConversationInput,
        chat_log: conversation.ChatLog,
    ) -> conversation.ConversationResult:
        """Call the API."""
        return self._async_get_result_from_chat_log(user_input, chat_log)


async def test_get_result_from_chat_log(
    hass: HomeAssistant,
    mock_conversation_input: conversation.ConversationInput,
) -> None:
    """Test getting result from chat log."""
    entity = TestEntity()
    intent_response = intent.IntentResponse(language="en")

    with (
        chat_session.async_get_chat_session(hass) as session,
        conversation.async_get_chat_log(
            hass, session, mock_conversation_input
        ) as chat_log,
    ):
        chat_log.content.extend(
            [
                conversation.ToolResultContent(
                    agent_id="mock-agent-id",
                    tool_call_id="mock-tool-call-id",
                    tool_name="mock-tool-name",
                    tool_result=llm.IntentResponseDict(intent_response),
                ),
                conversation.AssistantContent(
                    agent_id="mock-agent-id",
                    content="This is a response.",
                ),
            ]
        )

        result = await entity._async_handle_message(mock_conversation_input, chat_log)

    # Original intent response is returned with speech set
    assert result.response is intent_response
    assert result.response.speech["plain"]["speech"] == "This is a response."
