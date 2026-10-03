from dispute_agent.sip_realtime import SipRealtimeGateway
from dispute_agent.voice_call import (
    VoiceAuthenticationMethod,
    VoiceCallService,
    VoiceCallStage,
    VoiceCallState,
)
from webapp.backend.demo_seed import seed_demo_customers
from webapp.backend.repositories.mock import MockCustomerRepository


def gabriel_repository() -> MockCustomerRepository:
    repository = MockCustomerRepository()
    seed_demo_customers(repository)
    return repository


def authenticate_by_phone() -> tuple[VoiceCallService, VoiceCallState]:
    calls = VoiceCallService(gabriel_repository())
    state = calls.start("5511981020050", call_id="gabriel-phone")
    return calls, state


def test_phone_authentication_uses_shared_backend_profile() -> None:
    _, state = authenticate_by_phone()

    assert state.stage is VoiceCallStage.AUTHENTICATED
    assert state.authentication_method is VoiceAuthenticationMethod.PHONE
    assert state.identity is not None
    assert state.identity.customer_id == "DEMO-BR-GABRIEL-123456"
    assert state.identity.first_name == "Gabriel"
    assert state.identity.last_name == "Silveira"
    assert state.identity.full_name == "Gabriel Silveira"
    assert state.identity.gender == "male"
    assert state.identity.age == 27
    assert state.identity.detected_accent == "portuguese"


def test_document_authentication_uses_same_shared_backend_profile() -> None:
    calls = VoiceCallService(gabriel_repository())
    state = calls.start("+551100000000", call_id="gabriel-document")
    state = calls.confirm_language(state.call_id)

    for key in "123456#":
        state, _ = calls.receive_dtmf(state.call_id, key)

    assert state.stage is VoiceCallStage.AUTHENTICATED
    assert state.authentication_method is VoiceAuthenticationMethod.DOCUMENT
    assert state.identity is not None
    assert state.identity.first_name == "Gabriel"
    assert state.identity.last_name == "Silveira"


def test_authenticated_greeting_uses_first_name_naturally() -> None:
    _, state = authenticate_by_phone()

    greeting = SipRealtimeGateway._message_for(state, "phone_auth_success")
    instructions = SipRealtimeGateway._system_instructions(state)

    assert greeting.startswith("Olá, Gabriel.")
    assert "Olá, Gabriel Silveira" not in greeting
    assert "First name: Gabriel" in instructions
    assert "Last name: Silveira" in instructions
    assert "Gender: male" in instructions
    assert "Age: 27" in instructions
    assert "Accent: portuguese" in instructions


def test_language_confirmation_only_offers_other_languages() -> None:
    calls = VoiceCallService(gabriel_repository())
    scenarios = (
        (
            "+5511981020051",
            "continuar neste idioma ou prefere mudar para inglês ou espanhol",
            "switch to English or Spanish",
        ),
        (
            "+573001112233",
            "continuar en este idioma o cambiar a inglés o portugués",
            "switch to English or Portuguese",
        ),
        (
            "+14155550123",
            "continue in this language, or switch to Portuguese or Spanish",
            "switch to Portuguese or Spanish",
        ),
    )

    for index, (phone, expected_opening, expected_instruction) in enumerate(scenarios):
        state = calls.start(phone, call_id=f"language-{index}")
        opening = SipRealtimeGateway._message_for(state, "opening")
        instructions = SipRealtimeGateway._system_instructions(state)

        assert expected_opening in opening
        assert expected_instruction in instructions
