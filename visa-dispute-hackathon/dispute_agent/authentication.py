"""Mock, name-based customer identification for the hackathon agent."""

from __future__ import annotations

import csv
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from .country_context import locale_for, opening_prompt
from .intent_classifier import (
    AnswerIntent,
    AnswerIntentClassifier,
    ClassificationError,
    ConfirmationClassifier,
    ConfirmationIntent,
)
from .language_classifier import LanguageClassificationError, LanguageClassifier
from .name_extractor import NameExtractionError, NameExtractor


class AuthStatus(StrEnum):
    NEEDS_NAME = "needs_name"
    NEEDS_CONFIRMATION = "needs_confirmation"
    AUTHENTICATED = "authenticated"
    NOT_FOUND = "not_found"
    AMBIGUOUS = "ambiguous"
    HUMAN_HANDOFF = "human_handoff"
    CANCELLED = "cancelled"


class Language(StrEnum):
    EN = "en"
    PT = "pt"
    ES = "es"


MESSAGES = {
    "en": {
        "start": "Hello. I can help you start a card dispute. To locate your demo profile, what is your full name? You can also ask why I need it or request a person.",
        "success": "Thanks, {name}. I located your profile for this demo. Next, I can retrieve your recent card transactions so you can choose the one with a problem.",
        "confirm_name": "I found the customer name {name}. Is that your correct full name? Please answer yes or no.",
        "name_denied": "Thanks for correcting me. Please say your correct full name, including all surnames.",
        "confirmation_unclear": "I need to confirm the name before continuing. Is {name} your correct full name? Please answer yes or no.",
        "already": "Your demo profile is already located as {name}.",
        "why": "I use your name only to locate a synthetic demo profile and its test transactions. Name-only identification is not secure enough for real banking. Would you like to continue by giving your full name, or speak with a person?",
        "silence_1": "I did not hear a response. When you are ready, please say or type your full name. You can also ask for a person.",
        "silence_2": "We may be having an audio or connection problem. You can repeat or type your full name, or ask for a person. I will not open any transactions until a profile is located.",
        "refusal": "That is okay. Without a full name I cannot locate the demo profile or show transactions. You can provide it now or ask for a person.",
        "unclear": "I could not identify a full name in that response. Please say your first name and all surnames, for example: 'My full name is Ana Silva.' You can also ask for a person.",
        "not_found": "I understood the name as {name}, but I could not find it in the customer database. Please check the name and try again with your first name and all surnames. You can also ask for a person.",
        "handoff_requested": "Of course. I am connecting you with a person now. This demo simulates the transfer, and I will pass along a short summary so you do not need to repeat the interaction.",
        "handoff_ambiguous": "I found more than one demo profile with that name. To protect the transaction list, I will connect you with a person to resolve it. The transfer is simulated in this demo.",
        "handoff_no_response": "We may have an audio or connection problem. I will connect you with a person. The transfer is simulated in this demo.",
        "handoff_refusal": "I cannot locate the demo profile without a name, so I will connect you with a person. The transfer is simulated in this demo.",
        "handoff_not_found": "I still could not locate the profile. I will connect you with a person and pass along the attempts already made. The transfer is simulated in this demo.",
        "handoff_unclear": "I am having trouble understanding the response, so I will connect you with a person. The transfer is simulated in this demo.",
        "handoff_system": "I am having a temporary problem understanding responses. I will connect you with a person instead. The transfer is simulated in this demo.",
        "cancelled": "Okay, I cancelled this demo interaction. No dispute was opened and no transaction was selected.",
        "restarted": "Okay, we can start again. What is your full name? You can also ask why I need it or request a person.",
    },
    "pt": {
        "start": "Olá. Posso ajudar a iniciar uma contestação de cartão. Para localizar seu perfil de demonstração, qual é o seu nome completo? Você também pode perguntar por que preciso dele ou pedir um atendente.",
        "success": "Obrigado, {name}. Localizei seu perfil nesta demonstração. Agora posso buscar suas transações recentes de cartão para você indicar qual apresenta o problema.",
        "confirm_name": "Encontrei o nome {name} na base de clientes. Esse é o seu nome completo correto? Responda sim ou não.",
        "name_denied": "Obrigado por me corrigir. Diga seu nome completo correto, incluindo todos os sobrenomes.",
        "confirmation_unclear": "Preciso confirmar o nome antes de continuar. {name} é o seu nome completo correto? Responda sim ou não.",
        "already": "Seu perfil de demonstração já foi localizado como {name}.",
        "why": "Uso seu nome somente para localizar um perfil sintético de demonstração e suas transações de teste. Identificação apenas pelo nome não é segura para um banco real. Você prefere informar seu nome completo ou falar com um atendente?",
        "silence_1": "Não ouvi uma resposta. Quando estiver pronto, diga ou digite seu nome completo. Você também pode pedir um atendente.",
        "silence_2": "Talvez haja um problema de áudio ou conexão. Você pode repetir ou digitar seu nome completo, ou pedir um atendente. Nenhuma transação será aberta antes de localizarmos um perfil.",
        "refusal": "Tudo bem. Sem o nome completo não consigo localizar o perfil de demonstração nem mostrar transações. Você pode informá-lo agora ou pedir um atendente.",
        "unclear": "Não consegui identificar um nome completo nessa resposta. Diga seu primeiro nome e todos os sobrenomes, por exemplo: 'Meu nome completo é Ana Silva.' Você também pode pedir um atendente.",
        "not_found": "Entendi o nome como {name}, mas não o encontrei na base de clientes. Confira o nome e tente novamente com seu primeiro nome e todos os sobrenomes. Você também pode pedir um atendente.",
        "handoff_requested": "Claro. Vou conectar você a um atendente. Nesta demonstração, a transferência é simulada e enviarei um resumo para que você não precise repetir a interação.",
        "handoff_ambiguous": "Encontrei mais de um perfil de demonstração com esse nome. Para proteger a lista de transações, vou encaminhar o caso a um atendente. A transferência é simulada nesta demonstração.",
        "handoff_no_response": "Talvez haja um problema de áudio ou conexão. Vou encaminhar você a um atendente. A transferência é simulada nesta demonstração.",
        "handoff_refusal": "Sem um nome não consigo localizar o perfil de demonstração. Vou encaminhar você a um atendente. A transferência é simulada nesta demonstração.",
        "handoff_not_found": "Ainda não localizei o perfil. Vou encaminhar você a um atendente e enviar as tentativas já realizadas. A transferência é simulada nesta demonstração.",
        "handoff_unclear": "Estou com dificuldade para entender a resposta. Vou encaminhar você a um atendente. A transferência é simulada nesta demonstração.",
        "handoff_system": "Estou com um problema temporário para entender respostas. Vou encaminhar você a um atendente. A transferência é simulada nesta demonstração.",
        "cancelled": "Certo, cancelei esta interação de demonstração. Nenhuma contestação foi aberta e nenhuma transação foi selecionada.",
        "restarted": "Certo, vamos começar de novo. Qual é o seu nome completo? Você também pode perguntar por que preciso dele ou pedir um atendente.",
    },
    "es": {
        "start": "Hola. Puedo ayudarte a iniciar una disputa de tarjeta. Para localizar tu perfil de demostración, ¿cuál es tu nombre completo? También puedes preguntar por qué lo necesito o pedir un asesor.",
        "success": "Gracias, {name}. Encontré tu perfil para esta demostración. Ahora puedo buscar tus transacciones recientes de tarjeta para que indiques cuál tiene el problema.",
        "confirm_name": "Encontré el nombre {name} en la base de clientes. ¿Ese es tu nombre completo correcto? Responde sí o no.",
        "name_denied": "Gracias por corregirme. Di tu nombre completo correcto, incluidos todos tus apellidos.",
        "confirmation_unclear": "Necesito confirmar el nombre antes de continuar. ¿{name} es tu nombre completo correcto? Responde sí o no.",
        "already": "Tu perfil de demostración ya fue localizado como {name}.",
        "why": "Uso tu nombre únicamente para localizar un perfil sintético de demostración y sus transacciones de prueba. Identificar a alguien solo por su nombre no es seguro para un banco real. ¿Prefieres dar tu nombre completo o hablar con un asesor?",
        "silence_1": "No escuché una respuesta. Cuando estés listo, di o escribe tu nombre completo. También puedes pedir un asesor.",
        "silence_2": "Tal vez haya un problema de audio o conexión. Puedes repetir o escribir tu nombre completo, o pedir un asesor. No abriré transacciones hasta localizar un perfil.",
        "refusal": "Está bien. Sin el nombre completo no puedo localizar el perfil de demostración ni mostrar transacciones. Puedes darlo ahora o pedir un asesor.",
        "unclear": "No pude identificar un nombre completo en esa respuesta. Di tu nombre y todos tus apellidos, por ejemplo: 'Mi nombre completo es Ana Silva.' También puedes pedir un asesor.",
        "not_found": "Entendí el nombre como {name}, pero no lo encontré en la base de clientes. Verifica el nombre e inténtalo otra vez con tu nombre y todos tus apellidos. También puedes pedir un asesor.",
        "handoff_requested": "Claro. Voy a conectarte con un asesor. En esta demostración la transferencia es simulada y enviaré un resumen para que no tengas que repetir la interacción.",
        "handoff_ambiguous": "Encontré más de un perfil de demostración con ese nombre. Para proteger la lista de transacciones, derivaré el caso a un asesor. La transferencia es simulada en esta demostración.",
        "handoff_no_response": "Tal vez haya un problema de audio o conexión. Voy a derivarte a un asesor. La transferencia es simulada en esta demostración.",
        "handoff_refusal": "Sin un nombre no puedo localizar el perfil de demostración. Voy a derivarte a un asesor. La transferencia es simulada en esta demostración.",
        "handoff_not_found": "Todavía no pude localizar el perfil. Voy a derivarte a un asesor y enviaré los intentos realizados. La transferencia es simulada en esta demostración.",
        "handoff_unclear": "Tengo dificultades para entender la respuesta. Voy a derivarte a un asesor. La transferencia es simulada en esta demostración.",
        "handoff_system": "Tengo un problema temporal para entender las respuestas. Voy a derivarte a un asesor. La transferencia es simulada en esta demostración.",
        "cancelled": "De acuerdo, cancelé esta interacción de demostración. No se abrió ningún reclamo ni se seleccionó ninguna transacción.",
        "restarted": "De acuerdo, empecemos de nuevo. ¿Cuál es tu nombre completo? También puedes preguntar por qué lo necesito o pedir un asesor.",
    },
}

# The base dictionaries remain the fallback; these overrides make the active
# call-center wording consistent with the caller's country and chosen language.
MESSAGES["en-US"] = {**MESSAGES["en"]}
MESSAGES["pt-BR"] = {**MESSAGES["pt"]}
MESSAGES["es-419"] = {**MESSAGES["es"]}
MESSAGES["es-CO"] = {
    **MESSAGES["es"],
    "start": "Hola. Puedo ayudarle a iniciar una reclamación sobre su tarjeta. Para localizar su perfil de demostración, ¿cuál es su nombre completo? También puede preguntar por qué lo necesito o pedir un asesor.",
    "confirm_name": "Encontré el nombre {name} en la base de clientes. ¿Ese es su nombre completo correcto? Responda sí o no.",
    "name_denied": "Gracias por corregirme. Dígame su nombre completo correcto, incluidos todos sus apellidos.",
    "confirmation_unclear": "Necesito confirmar el nombre antes de continuar. ¿{name} es su nombre completo correcto? Responda sí o no.",
    "not_found": "Entendí el nombre como {name}, pero no lo encontré en la base de clientes. Verifique el nombre e inténtelo otra vez con su nombre y todos sus apellidos. También puede pedir un asesor.",
}
MESSAGES["es-MX"] = {
    **MESSAGES["es"],
    "start": "Hola. Puedo ayudarle a iniciar una aclaración de tarjeta. Para localizar su perfil de demostración, ¿cuál es su nombre completo? También puede preguntar por qué lo necesito o pedir un asesor.",
    "confirm_name": "Encontré el nombre {name} en la base de clientes. ¿Ese es su nombre completo correcto? Responda sí o no.",
    "name_denied": "Gracias por corregirme. Dígame su nombre completo correcto, incluidos todos sus apellidos.",
    "confirmation_unclear": "Necesito confirmar el nombre antes de continuar. ¿{name} es su nombre completo correcto? Responda sí o no.",
    "not_found": "Entendí el nombre como {name}, pero no lo encontré en la base de clientes. Revise el nombre e inténtelo de nuevo con su nombre y todos sus apellidos. También puede pedir un asesor.",
}
MESSAGES["es-AR"] = {
    **MESSAGES["es"],
    "start": "Hola. Puedo ayudarte a iniciar un reclamo por una tarjeta. Para encontrar tu perfil de demostración, ¿cuál es tu nombre completo? También podés preguntar por qué lo necesito o pedir hablar con una persona.",
    "confirm_name": "Encontré el nombre {name} en la base de clientes. ¿Ese es tu nombre completo correcto? Respondé sí o no.",
    "name_denied": "Gracias por corregirme. Decime tu nombre completo correcto, incluidos todos tus apellidos.",
    "confirmation_unclear": "Necesito confirmar el nombre antes de continuar. ¿{name} es tu nombre completo correcto? Respondé sí o no.",
    "not_found": "Entendí el nombre como {name}, pero no lo encontré en la base de clientes. Revisá el nombre e intentá otra vez con tu nombre y todos tus apellidos. También podés pedir hablar con una persona.",
}

_FORMAL_SPANISH = {
    "success": "Gracias, {name}. Encontré su perfil para esta demostración. Ahora puedo buscar sus transacciones recientes de tarjeta para que indique cuál tiene el problema.",
    "already": "Su perfil de demostración ya fue localizado como {name}.",
    "why": "Uso su nombre únicamente para localizar un perfil sintético de demostración y sus transacciones de prueba. Identificar a alguien solo por su nombre no es seguro para un banco real. ¿Prefiere dar su nombre completo o hablar con un asesor?",
    "silence_1": "No escuché una respuesta. Cuando esté listo, diga o escriba su nombre completo. También puede pedir un asesor.",
    "silence_2": "Tal vez haya un problema de audio o conexión. Puede repetir o escribir su nombre completo, o pedir un asesor. No abriré transacciones hasta localizar un perfil.",
    "refusal": "Está bien. Sin el nombre completo no puedo localizar el perfil de demostración ni mostrar transacciones. Puede darlo ahora o pedir un asesor.",
    "unclear": "No pude identificar un nombre completo en esa respuesta. Diga su nombre y todos sus apellidos, por ejemplo: 'Mi nombre completo es Ana Silva.' También puede pedir un asesor.",
    "handoff_requested": "Claro. Voy a conectarle con un asesor. En esta demostración la transferencia es simulada y enviaré un resumen para que no tenga que repetir la interacción.",
}
MESSAGES["es-CO"].update(_FORMAL_SPANISH)
MESSAGES["es-MX"].update(_FORMAL_SPANISH)

MESSAGES["es-AR"].update(
    {
        "why": "Uso tu nombre solamente para encontrar un perfil sintético de demostración y sus transacciones de prueba. Identificar a alguien solo por su nombre no es seguro para un banco real. ¿Preferís dar tu nombre completo o hablar con una persona?",
        "silence_1": "No escuché una respuesta. Cuando estés listo, decí o escribí tu nombre completo. También podés pedir hablar con una persona.",
        "silence_2": "Tal vez haya un problema de audio o conexión. Podés repetir o escribir tu nombre completo, o pedir hablar con una persona. No voy a abrir transacciones hasta encontrar un perfil.",
        "refusal": "Está bien. Sin el nombre completo no puedo encontrar el perfil de demostración ni mostrar transacciones. Podés darlo ahora o pedir hablar con una persona.",
        "unclear": "No pude identificar un nombre completo en esa respuesta. Decí tu nombre y todos tus apellidos, por ejemplo: 'Mi nombre completo es Ana Silva.' También podés pedir hablar con una persona.",
    }
)

AUTO_LANGUAGE_PROMPT = (
    "Choose a language: English, Portuguese, or Spanish. / "
    "Escolha um idioma: Inglês, Português ou Espanhol. / "
    "Elige un idioma: Inglés, Portugués o Español."
)

AUTO_LANGUAGE_RETRY = (
    "I did not recognize the language. Say English, Portuguese, or Spanish. / "
    "Não reconheci o idioma. Diga Inglês, Português ou Espanhol. / "
    "No reconocí el idioma. Di Inglés, Portugués o Español."
)


@dataclass(frozen=True)
class CustomerMatch:
    customer_id: str
    full_name: str


@dataclass(frozen=True)
class AuthenticationResult:
    status: AuthStatus
    message: str
    customer: CustomerMatch | None = None
    assurance_level: str | None = None
    handoff_summary: dict[str, str | int | None] | None = None

    @property
    def authenticated(self) -> bool:
        return self.status is AuthStatus.AUTHENTICATED


def normalize_name(value: str) -> str:
    """Normalize spacing, case and diacritics for deterministic name matching."""

    value = unicodedata.normalize("NFKD", value)
    value = "".join(character for character in value if not unicodedata.combining(character))
    value = value.casefold()
    value = "".join(
        character if character.isalnum() or character in " '-_" else " " for character in value
    )
    return " ".join(value.split())


class CustomerDirectory:
    """Read-only name index backed by the synthetic customers CSV."""

    def __init__(self, customers_csv: str | Path):
        self.customers_csv = Path(customers_csv)
        self._customers_by_name = self._load()

    def _load(self) -> dict[str, list[CustomerMatch]]:
        if not self.customers_csv.is_file():
            raise FileNotFoundError(f"Customers CSV not found: {self.customers_csv}")
        index: dict[str, list[CustomerMatch]] = {}
        with self.customers_csv.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            required = {"customer_id", "first_name", "last_name"}
            missing = required.difference(reader.fieldnames or [])
            if missing:
                raise ValueError(f"Customers CSV is missing columns: {sorted(missing)}")
            for row in reader:
                full_name = " ".join((row["first_name"].strip(), row["last_name"].strip()))
                key = normalize_name(full_name)
                if key:
                    index.setdefault(key, []).append(
                        CustomerMatch(customer_id=row["customer_id"], full_name=full_name)
                    )
        return index

    def find_by_full_name(self, full_name: str) -> list[CustomerMatch]:
        return list(self._customers_by_name.get(normalize_name(full_name), []))


class AuthenticationAgent:
    """Stateful demo-only name-identification conversation for one caller."""

    QUESTION = "What is your full name?"

    def __init__(
        self,
        customers_csv: str | Path,
        intent_classifier: AnswerIntentClassifier,
        *,
        min_intent_confidence: float = 0.55,
        max_failed_attempts: int = 3,
        max_avoidance_attempts: int = 2,
        max_no_response_attempts: int = 3,
        max_unclear_attempts: int = 2,
        language: str = "en",
        language_classifier: LanguageClassifier | None = None,
        min_language_confidence: float = 0.65,
        name_extractor: NameExtractor | None = None,
        country_code: str | None = None,
        confirmation_classifier: ConfirmationClassifier | None = None,
        min_confirmation_confidence: float = 0.35,
        min_confirmation_margin: float = 0.05,
    ):
        self.directory = CustomerDirectory(customers_csv)
        self.intent_classifier = intent_classifier
        self.min_intent_confidence = min_intent_confidence
        self.max_failed_attempts = max_failed_attempts
        self.max_avoidance_attempts = max_avoidance_attempts
        self.max_no_response_attempts = max_no_response_attempts
        self.max_unclear_attempts = max_unclear_attempts
        self.failed_attempts = 0
        self.avoidance_attempts = 0
        self.no_response_attempts = 0
        self.unclear_attempts = 0
        self.current_customer: CustomerMatch | None = None
        self.language = language if language in {"en", "pt", "es", "auto"} else "en"
        self.language_classifier = language_classifier
        self.min_language_confidence = min_language_confidence
        self.name_extractor = name_extractor
        self.country_code = country_code
        self.locale = (
            locale_for(self.language, country_code) if self.language != "auto" else "en-US"
        )
        self.confirmation_classifier = confirmation_classifier
        self.min_confirmation_confidence = min_confirmation_confidence
        self.min_confirmation_margin = min_confirmation_margin
        self.pending_customer: CustomerMatch | None = None
        self.last_claimed_name: str | None = None
        self.last_customer_utterance: str | None = None
        self.last_agent_message: str | None = None
        self.questions_answered = 0

    def _message(self, key: str, **values: str) -> str:
        return MESSAGES[self.locale][key].format(**values)

    def _handoff(self, key: str, reason: str) -> AuthenticationResult:
        return AuthenticationResult(
            AuthStatus.HUMAN_HANDOFF,
            self._message(key),
            handoff_summary={
                "language": "en" if self.language == "auto" else self.language,
                "locale": self.locale,
                "reason": reason,
                "name_provided": self.last_claimed_name,
                "failed_name_attempts": self.failed_attempts,
                "no_response_attempts": self.no_response_attempts,
                "avoidance_attempts": self.avoidance_attempts,
                "unclear_attempts": self.unclear_attempts,
                "recommended_next_step": "Human verifies identity with the mocked fallback process before showing transactions.",
                "phase": "name_confirmation" if self.pending_customer else "name_collection",
                "matched_candidate": self.pending_customer.full_name
                if self.pending_customer
                else None,
                "confirmation_status": "pending" if self.pending_customer else "not_started",
                "last_customer_utterance": self.last_customer_utterance,
                "previous_agent_message": self.last_agent_message,
                "questions_answered": self.questions_answered,
            },
        )

    def _reset_identification(self) -> AuthenticationResult:
        self.pending_customer = None
        self.last_claimed_name = None
        self.failed_attempts = 0
        self.avoidance_attempts = 0
        self.no_response_attempts = 0
        self.unclear_attempts = 0
        return AuthenticationResult(AuthStatus.NEEDS_NAME, self._message("restarted"))

    def apply_global_control(self, intent: AnswerIntent) -> AuthenticationResult | None:
        if intent is AnswerIntent.REQUESTS_HUMAN:
            return self._handoff("handoff_requested", "customer_requested_human")
        if intent is AnswerIntent.CANCELS:
            self.pending_customer = None
            return AuthenticationResult(AuthStatus.CANCELLED, self._message("cancelled"))
        if intent is AnswerIntent.RESTARTS:
            return self._reset_identification()
        return None

    def classify_global_control(self, answer: str) -> AnswerIntent | None:
        """Return only a control decision that passes the normal confidence gate."""

        decision = self.intent_classifier.classify(answer)
        if (
            decision.intent
            in {AnswerIntent.REQUESTS_HUMAN, AnswerIntent.CANCELS, AnswerIntent.RESTARTS}
            and decision.confidence >= self.min_intent_confidence
        ):
            return decision.intent
        return None

    def _extract_name(self, answer: str) -> str | None:
        if self.name_extractor is None:
            return None
        try:
            return self.name_extractor.extract(answer)
        except NameExtractionError:
            return None

    def _match_claimed_name(self, claimed_name: str) -> AuthenticationResult | None:
        matches = self.directory.find_by_full_name(claimed_name)
        if len(matches) == 1:
            if self.confirmation_classifier is not None:
                self.pending_customer = matches[0]
                return AuthenticationResult(
                    AuthStatus.NEEDS_CONFIRMATION,
                    self._message("confirm_name", name=matches[0].full_name),
                )
            return self._authenticate(matches[0], confirmed=False)
        if len(matches) > 1:
            self.last_claimed_name = claimed_name
            return self._handoff("handoff_ambiguous", "duplicate_name")
        return None

    def _authenticate(
        self, customer: CustomerMatch, *, confirmed: bool = True
    ) -> AuthenticationResult:
        self.current_customer = customer
        self.pending_customer = None
        return AuthenticationResult(
            AuthStatus.AUTHENTICATED,
            self._message("success", name=customer.full_name),
            customer,
            "DEMO_ONLY_NAME_MATCH_CONFIRMED" if confirmed else "DEMO_ONLY_NAME_MATCH",
        )

    def _handle_confirmation(self, answer: str) -> AuthenticationResult:
        assert self.pending_customer is not None
        customer = self.pending_customer
        try:
            control_intent = self.classify_global_control(answer)
        except ClassificationError:
            control_intent = None
        control = self.apply_global_control(control_intent) if control_intent is not None else None
        if control is not None:
            return control
        corrected_name = self._extract_name(answer)
        if corrected_name and normalize_name(corrected_name) != normalize_name(customer.full_name):
            self.pending_customer = None
            corrected_result = self._match_claimed_name(corrected_name)
            if corrected_result is not None:
                return corrected_result
            return self._name_not_found(corrected_name)
        try:
            decision = self.confirmation_classifier.classify(answer)
        except ClassificationError:
            return self._handoff("handoff_system", "confirmation_model_unavailable")
        if (
            decision.confidence < self.min_confirmation_confidence
            or decision.confidence - sorted(decision.probabilities.values(), reverse=True)[1]
            < self.min_confirmation_margin
            or decision.intent is ConfirmationIntent.OTHER
        ):
            return AuthenticationResult(
                AuthStatus.NEEDS_CONFIRMATION,
                self._message("confirmation_unclear", name=customer.full_name),
            )
        return self.apply_validated_confirmation(answer, decision.intent)

    def apply_validated_confirmation(
        self, answer: str, intent: ConfirmationIntent
    ) -> AuthenticationResult:
        """Apply one confirmation decision already accepted by the graph gate."""

        assert self.pending_customer is not None
        customer = self.pending_customer
        corrected_name = self._extract_name(answer)
        if corrected_name and normalize_name(corrected_name) != normalize_name(customer.full_name):
            self.pending_customer = None
            corrected_result = self._match_claimed_name(corrected_name)
            if corrected_result is not None:
                return corrected_result
            return self._name_not_found(corrected_name)
        if intent is ConfirmationIntent.CONFIRMS:
            return self._authenticate(customer)

        self.pending_customer = None
        corrected_name = corrected_name or self._extract_name(answer)
        if corrected_name:
            corrected_result = self._match_claimed_name(corrected_name)
            if corrected_result is not None:
                return corrected_result
            return self._name_not_found(corrected_name)
        return AuthenticationResult(AuthStatus.NEEDS_NAME, self._message("name_denied"))

    def apply_validated_intent(self, answer: str, intent: AnswerIntent) -> AuthenticationResult:
        """Apply one non-OTHER intent already accepted by the graph gate."""

        control = self.apply_global_control(intent)
        if control is not None:
            return control
        if intent is AnswerIntent.ASKS_WHY:
            return AuthenticationResult(AuthStatus.NEEDS_NAME, self._message("why"))
        if intent is AnswerIntent.AVOIDS_ANSWER:
            self.avoidance_attempts += 1
            if self.avoidance_attempts >= self.max_avoidance_attempts:
                return self._handoff("handoff_refusal", "name_not_provided")
            return AuthenticationResult(AuthStatus.NEEDS_NAME, self._message("refusal"))

        claimed_name = self._extract_name(answer) or answer
        matched_result = self._match_claimed_name(claimed_name)
        if matched_result is not None:
            return matched_result
        return self._name_not_found(claimed_name)

    @staticmethod
    def _looks_like_standalone_name(answer: str) -> bool:
        words = normalize_name(answer).split()
        if not 2 <= len(words) <= 6:
            return False
        conversational_words = {
            "i",
            "my",
            "name",
            "is",
            "why",
            "what",
            "need",
            "want",
            "maybe",
            "later",
            "meu",
            "minha",
            "nome",
            "e",
            "porque",
            "precisa",
            "quero",
            "talvez",
            "depois",
            "mi",
            "nombre",
            "es",
            "por",
            "que",
            "necesita",
            "quiero",
            "quizas",
            "luego",
        }
        return not any(word in conversational_words for word in words)

    def _name_not_found(self, claimed_name: str) -> AuthenticationResult:
        self.last_claimed_name = claimed_name
        self.failed_attempts += 1
        if self.failed_attempts >= self.max_failed_attempts:
            return self._handoff("handoff_not_found", "name_not_found_after_retries")
        return AuthenticationResult(
            AuthStatus.NOT_FOUND,
            self._message("not_found", name=claimed_name),
        )

    def start(self) -> AuthenticationResult:
        if self.language == "auto":
            prompt = (
                opening_prompt(self.country_code) if self.country_code else AUTO_LANGUAGE_PROMPT
            )
            return AuthenticationResult(AuthStatus.NEEDS_NAME, prompt)
        return AuthenticationResult(AuthStatus.NEEDS_NAME, self._message("start"))

    def handle_answer(self, answer: str | None) -> AuthenticationResult:
        self.last_customer_utterance = (answer or "").strip() or None
        if self.current_customer is not None:
            return AuthenticationResult(
                AuthStatus.AUTHENTICATED,
                self._message("already", name=self.current_customer.full_name),
                self.current_customer,
                "DEMO_ONLY_NAME_MATCH",
            )

        answer = (answer or "").strip()
        if not answer:
            self.no_response_attempts += 1
            if self.no_response_attempts >= self.max_no_response_attempts:
                return self._handoff("handoff_no_response", "repeated_no_response")
            key = "silence_1" if self.no_response_attempts == 1 else "silence_2"
            return AuthenticationResult(AuthStatus.NEEDS_NAME, self._message(key))
        else:
            if self.pending_customer is not None:
                return self._handle_confirmation(answer)
            if self.language == "auto":
                selected_language = normalize_name(answer)
                language_markers = {
                    "en": {"english", "ingles", "en"},
                    "pt": {"portugues", "portuguese", "brasileiro", "brasileira", "pt"},
                    "es": {"espanol", "spanish", "castellano", "es"},
                }
                words = set(selected_language.split())
                selected = next(
                    (locale for locale, markers in language_markers.items() if words & markers),
                    None,
                )
                if selected is not None:
                    self.language = selected
                    self.locale = locale_for(selected, self.country_code)
                    return AuthenticationResult(AuthStatus.NEEDS_NAME, self._message("start"))
                if self.language_classifier is None:
                    return AuthenticationResult(AuthStatus.NEEDS_NAME, AUTO_LANGUAGE_RETRY)
                try:
                    language_decision = self.language_classifier.classify(answer)
                except LanguageClassificationError:
                    return AuthenticationResult(AuthStatus.NEEDS_NAME, AUTO_LANGUAGE_RETRY)
                if (
                    language_decision.language not in {"en", "pt", "es"}
                    or language_decision.confidence < self.min_language_confidence
                ):
                    return AuthenticationResult(AuthStatus.NEEDS_NAME, AUTO_LANGUAGE_RETRY)
                self.language = language_decision.language
                self.locale = locale_for(self.language, self.country_code)
            matches = self.directory.find_by_full_name(answer)
            if len(matches) == 1:
                return self._match_claimed_name(answer)
            if len(matches) > 1:
                self.last_claimed_name = answer
                return self._handoff("handoff_ambiguous", "duplicate_name")

            try:
                decision = self.intent_classifier.classify(answer)
            except ClassificationError:
                return self._handoff("handoff_system", "intent_service_unavailable")
            if decision.confidence < self.min_intent_confidence:
                extracted_name = self._extract_name(answer)
                if extracted_name:
                    matched_result = self._match_claimed_name(extracted_name)
                    if matched_result is not None:
                        return matched_result
                    return self._name_not_found(extracted_name)
                if self._looks_like_standalone_name(answer):
                    return self._name_not_found(answer)
                self.unclear_attempts += 1
                if self.unclear_attempts >= self.max_unclear_attempts:
                    return self._handoff("handoff_unclear", "repeated_unclear_response")
                return AuthenticationResult(AuthStatus.NEEDS_NAME, self._message("unclear"))
            intent = decision.intent

        if intent is AnswerIntent.OTHER:
            extracted_name = self._extract_name(answer)
            if extracted_name:
                matched_result = self._match_claimed_name(extracted_name)
                if matched_result is not None:
                    return matched_result
                return self._name_not_found(extracted_name)
            if self._looks_like_standalone_name(answer):
                return self._name_not_found(answer)
            self.unclear_attempts += 1
            if self.unclear_attempts >= self.max_unclear_attempts:
                return self._handoff("handoff_unclear", "repeated_unclear_response")
            return AuthenticationResult(AuthStatus.NEEDS_NAME, self._message("unclear"))

        return self.apply_validated_intent(answer, intent)
