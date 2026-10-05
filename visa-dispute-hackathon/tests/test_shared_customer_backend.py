from fakes import InMemoryCustomerRepository, seed_demo_customers, voice_repositories

from dispute_agent.sip_realtime import SipRealtimeGateway
from dispute_agent.voice_call import (
    VoiceAuthenticationMethod,
    VoiceCallService,
    VoiceCallStage,
    VoiceCallState,
)

GABRIEL_ID = "DEMO-BR-GABRIEL-123456"


def gabriel_repository() -> InMemoryCustomerRepository:
    repository = InMemoryCustomerRepository()
    seed_demo_customers(repository)
    return repository


def authenticate_by_phone() -> tuple[VoiceCallService, VoiceCallState]:
    calls = VoiceCallService(gabriel_repository(), **voice_repositories(GABRIEL_ID))
    state = calls.start("5511981020050", call_id="gabriel-phone")
    state = calls.confirm_language(state.call_id)
    state = calls.choose_authentication_method(state.call_id, method="phone")
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


def test_known_phone_uses_profile_locale_and_skips_language_question() -> None:
    calls = VoiceCallService(gabriel_repository(), **voice_repositories(GABRIEL_ID))
    state = calls.start("5511981020050", call_id="gabriel-locale-only")

    assert state.stage is VoiceCallStage.NEEDS_AUTH_METHOD
    assert state.identity is None
    assert state.authentication_method is None
    assert (state.locale.language, state.locale.locale, state.locale.accent) == (
        "pt",
        "pt-BR",
        "brazilian",
    )
    opening = SipRealtimeGateway._message_for(state, "opening")
    assert "português brasileiro" in opening
    assert "prefere mudar" not in opening
    assert "autenticação pelo número desta ligação é automática" in opening
    assert "Factored ID" in opening
    assert opening.endswith("Qual opção prefere: telefone ou documento?")
    assert "pode pedir um atendente humano" in opening


def test_document_authentication_uses_same_shared_backend_profile() -> None:
    calls = VoiceCallService(gabriel_repository(), **voice_repositories(GABRIEL_ID))
    state = calls.start("+551100000000", call_id="gabriel-document")
    state = calls.confirm_language(state.call_id)
    state = calls.choose_authentication_method(state.call_id, method="document")

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
    calls = VoiceCallService(gabriel_repository(), **voice_repositories(GABRIEL_ID))
    scenarios = (
        (
            "+551100000001",
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


def test_registered_phones_use_each_profiles_regional_accent() -> None:
    calls = VoiceCallService(gabriel_repository(), **voice_repositories(GABRIEL_ID))
    scenarios = (
        ("+5511981020050", "pt-BR", "brazilian"),
        ("+573009000001", "es-CO", "colombian"),
        ("+525590000001", "es-MX", "mexican"),
        ("+15129000001", "en-US", "american"),
    )

    for index, (phone, locale, accent) in enumerate(scenarios):
        state = calls.start(phone, call_id=f"registered-accent-{index}")

        assert state.stage is VoiceCallStage.NEEDS_AUTH_METHOD
        assert state.identity is None
        assert (state.locale.locale, state.locale.accent) == (locale, accent)
        assert "human" in SipRealtimeGateway._system_instructions(state).lower()
