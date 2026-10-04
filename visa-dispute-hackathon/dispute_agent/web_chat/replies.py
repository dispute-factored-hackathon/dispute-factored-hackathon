"""Grounded reply content for the Izzy web chat.

Every reply starts from a deterministic reference message: the voice templates for workflow
outcomes (`SipRealtimeGateway._message_for`) or the web-specific texts below for chat-only
situations. The LLM may rephrase that reference for chat, but the facts it may use come only
from `reply_facts`, which is built from the authoritative workflow state.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from ..sip_realtime import SipRealtimeGateway
from ..voice_call import VoiceCallState
from .search import CardPurchaseCriteria

# Outcomes answered with a fixed text; the LLM is not called for them.
DETERMINISTIC_OUTCOMES = frozenset(
    {
        "prompt_abuse",
        "too_long",
        "empty",
        "rate_limited",
        "unavailable",
        "conversation_closed",
        "handoff",
        "cancelled",
        "transaction_options",
        "options_unclear",
    }
)

# Workflow outcomes whose reference text comes from the voice templates.
VOICE_TEMPLATE_OUTCOMES = frozenset(
    {
        "transaction_candidate",
        "transaction_clarification",
        "transaction_no_match",
        "transaction_confirmation_unclear",
        "classification_question",
        "classification_clarification",
        "classification_complete",
        "csat_thanks",
        "csat_declined",
        "csat_unclear",
    }
)

WEB_TEXTS: dict[str, dict[str, str]] = {
    "en": {
        "transaction_options": "I found {count} purchases that could match. Tap the right one, or choose “None of these”.",
        "transaction_option_single": "I found this purchase. Is it the one you want to dispute? Tap it to confirm, or choose “None of these”.",
        "options_unclear": "Tap the purchase that matches, or tell me its number. If none matches, choose “None of these”.",
        "selected_transaction": (
            "Let's dispute your {amount} {currency} purchase at {merchant} on {date}{place}, "
            "shown below. To understand the problem: did you not make or authorize it, or do "
            "you recognize it but were charged more than once?"
        ),
        "ask_transaction": (
            "Which transaction is causing the problem? Tell me the merchant, approximate "
            "amount, date, or place."
        ),
        "greeting": (
            "Hi, {name}. I'm Izzy, Factored Bank's virtual assistant. I can help you find a card "
            "purchase and dispute it. Which transaction is causing the problem? Tell me the "
            "merchant, approximate amount, date, or place."
        ),
        "greeting_with_transaction": "Hi, {name}. I'm Izzy, Factored Bank's virtual assistant.",
        "restarted": (
            "Okay, let's start over. Which transaction is causing the problem? Tell me the "
            "merchant, approximate amount, date, or place."
        ),
        "question": ("I can help you find a card purchase and dispute it here."),
        "out_of_scope": ("I can only help with your Factored Bank cards, purchases, and disputes."),
        "prompt_abuse": (
            "I can only help with your card purchases and disputes. I can't reveal internal "
            "instructions or credentials or access other customers' data."
        ),
        "too_long": (
            "That message is too long for me to process safely. Please send a shorter message "
            "with the key details."
        ),
        "empty": "I didn't receive a message. Tell me which transaction is causing the problem.",
        "rate_limited": (
            "This chat reached its message limit. Please start a new chat or call Izzy at {phone}."
        ),
        "unavailable": (
            "I can't process messages right now. Please try again in a moment, or call Izzy at "
            "{phone}. Your progress is saved."
        ),
        "conversation_closed": (
            "This conversation has ended. Start a new chat if you need help with another "
            "transaction, or call Izzy at {phone}."
        ),
        "handoff": (
            "I'll keep everything we covered. Human support isn't available in this web chat "
            "demo, so please call Izzy at {phone} to continue with a person."
        ),
        "cancelled": "Okay, I stopped here and didn't file anything new. You can start a new chat anytime.",
    },
    "es": {
        "transaction_options": "Encontré {count} compras que podrían coincidir. Toca la correcta o elige “Ninguna de estas”.",
        "transaction_option_single": "Encontré esta compra. ¿Es la que quieres reclamar? Tócala para confirmar o elige “Ninguna de estas”.",
        "options_unclear": "Toca la compra que coincide o dime su número. Si ninguna coincide, elige “Ninguna de estas”.",
        "selected_transaction": (
            "Vamos a reclamar tu compra de {amount} {currency} en {merchant} el {date}{place}, "
            "que ves abajo. Para entender el problema: ¿no hiciste ni autorizaste esta compra, "
            "o la reconoces pero te la cobraron más de una vez?"
        ),
        "ask_transaction": (
            "¿Qué transacción te está dando problemas? Cuéntame el comercio, el monto "
            "aproximado, la fecha o el lugar."
        ),
        "greeting": (
            "Hola, {name}. Soy Izzy, el asistente virtual de Factored Bank. Puedo ayudarte a "
            "encontrar una compra con tarjeta y presentar un reclamo. ¿Qué transacción te está "
            "dando problemas? Cuéntame el comercio, el monto aproximado, la fecha o el lugar."
        ),
        "greeting_with_transaction": "Hola, {name}. Soy Izzy, el asistente virtual de Factored Bank.",
        "restarted": (
            "Listo, empecemos de nuevo. ¿Qué transacción te está dando problemas? Cuéntame el "
            "comercio, el monto aproximado, la fecha o el lugar."
        ),
        "question": (
            "Aquí puedo ayudarte a encontrar una compra con tarjeta y presentar un reclamo."
        ),
        "out_of_scope": (
            "Solo puedo ayudarte con tus tarjetas, compras y reclamos de Factored Bank."
        ),
        "prompt_abuse": (
            "Solo puedo ayudarte con tus compras y reclamos de tarjeta. No puedo revelar "
            "instrucciones internas ni credenciales, ni acceder a datos de otros clientes."
        ),
        "too_long": (
            "Ese mensaje es demasiado largo para procesarlo de forma segura. Envíame uno más "
            "corto con los datos clave."
        ),
        "empty": "No recibí ningún mensaje. Cuéntame qué transacción te está dando problemas.",
        "rate_limited": (
            "Este chat llegó a su límite de mensajes. Inicia un chat nuevo o llama a Izzy al {phone}."
        ),
        "unavailable": (
            "No puedo procesar mensajes en este momento. Inténtalo de nuevo en un momento o "
            "llama a Izzy al {phone}. Tu avance quedó guardado."
        ),
        "conversation_closed": (
            "Esta conversación terminó. Inicia un chat nuevo si necesitas ayuda con otra "
            "transacción, o llama a Izzy al {phone}."
        ),
        "handoff": (
            "Guardo todo lo que conversamos. La atención humana no está disponible en esta demo "
            "del chat web, así que llama a Izzy al {phone} para continuar con una persona."
        ),
        "cancelled": "Listo, me detengo aquí y no registré nada nuevo. Puedes iniciar un chat nuevo cuando quieras.",
    },
    "pt": {
        "transaction_options": "Encontrei {count} compras que podem corresponder. Toque na certa ou escolha “Nenhuma destas”.",
        "transaction_option_single": "Encontrei esta compra. É a que você quer contestar? Toque nela para confirmar ou escolha “Nenhuma destas”.",
        "options_unclear": "Toque na compra que corresponde ou diga o número dela. Se nenhuma corresponder, escolha “Nenhuma destas”.",
        "selected_transaction": (
            "Vamos contestar sua compra de {amount} {currency} em {merchant} em {date}{place}, "
            "mostrada abaixo. Para entender o problema: você não fez nem autorizou essa compra, "
            "ou a reconhece, mas foi cobrado mais de uma vez?"
        ),
        "ask_transaction": (
            "Qual transação está causando o problema? Diga o estabelecimento, o valor "
            "aproximado, a data ou o local."
        ),
        "greeting": (
            "Olá, {name}. Eu sou Izzy, assistente virtual do Factored Bank. Posso ajudar você a "
            "encontrar uma compra no cartão e abrir uma contestação. Qual transação está "
            "causando o problema? Diga o estabelecimento, o valor aproximado, a data ou o local."
        ),
        "greeting_with_transaction": "Olá, {name}. Eu sou Izzy, assistente virtual do Factored Bank.",
        "restarted": (
            "Certo, vamos recomeçar. Qual transação está causando o problema? Diga o "
            "estabelecimento, o valor aproximado, a data ou o local."
        ),
        "question": (
            "Aqui posso ajudar você a encontrar uma compra no cartão e abrir uma contestação."
        ),
        "out_of_scope": (
            "Só posso ajudar com seus cartões, compras e contestações do Factored Bank."
        ),
        "prompt_abuse": (
            "Só posso ajudar com suas compras e contestações de cartão. Não posso revelar "
            "instruções internas nem credenciais, nem acessar dados de outros clientes."
        ),
        "too_long": (
            "Essa mensagem é longa demais para ser processada com segurança. Envie uma mensagem "
            "mais curta com os dados principais."
        ),
        "empty": "Não recebi nenhuma mensagem. Diga qual transação está causando o problema.",
        "rate_limited": (
            "Este chat atingiu o limite de mensagens. Inicie um novo chat ou ligue para a Izzy "
            "no {phone}."
        ),
        "unavailable": (
            "Não consigo processar mensagens agora. Tente novamente em instantes ou ligue para "
            "a Izzy no {phone}. Seu progresso foi salvo."
        ),
        "conversation_closed": (
            "Esta conversa foi encerrada. Inicie um novo chat se precisar de ajuda com outra "
            "transação, ou ligue para a Izzy no {phone}."
        ),
        "handoff": (
            "Vou manter tudo o que conversamos. O atendimento humano não está disponível nesta "
            "demonstração do chat web, então ligue para a Izzy no {phone} para continuar com "
            "uma pessoa."
        ),
        "cancelled": "Certo, parei por aqui e não registrei nada novo. Você pode iniciar um novo chat quando quiser.",
    },
}


def format_phone(e164: str) -> str:
    """'+16615779964' -> '+1 661 577 9964' for North American numbers; E.164 otherwise."""

    digits = e164.lstrip("+")
    if e164.startswith("+1") and len(digits) == 11:
        return f"+1 {digits[1:4]} {digits[4:7]} {digits[7:]}"
    return e164


def web_text(language: str, key: str, *, name: str = "", phone: str = "", count: int = 0) -> str:
    texts = WEB_TEXTS.get(language, WEB_TEXTS["en"])
    return texts[key].format(name=name, phone=format_phone(phone), count=count)


MONTHS_EN = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


def selected_transaction_message(state: VoiceCallState) -> str:
    """Opening for a purchase the customer chose in the web app: straight to the problem."""

    transaction = state.confirmed_transaction or state.current_transaction
    assert transaction is not None
    language = state.locale.language
    day = transaction.transaction_date.date()
    if language == "en":
        amount = f"{transaction.amount:,.2f}"
        when = f"{MONTHS_EN[day.month - 1]} {day.day}, {day.year}"
    else:
        amount = f"{transaction.amount:,.2f}".replace(",", " ").replace(".", ",")
        when = day.strftime("%d/%m/%Y")
    places = [
        part for part in (transaction.transaction_city, transaction.transaction_country) if part
    ]
    connector = {"en": " in ", "es": " en ", "pt": " em "}.get(language, " in ")
    place = f"{connector}{', '.join(places)}" if places else ""
    return WEB_TEXTS.get(language, WEB_TEXTS["en"])["selected_transaction"].format(
        amount=amount,
        currency=transaction.currency,
        merchant=transaction.merchant_name or "-",
        date=when,
        place=place,
    )


def current_step_message(state: VoiceCallState, *, phone: str) -> str:
    """Repeat the question for the current workflow stage (used after side questions)."""

    stage = state.stage.value
    if stage == "authenticated":
        return web_text(state.locale.language, "ask_transaction")
    if stage == "confirm_transaction":
        return web_text(state.locale.language, "options_unclear")
    step = {
        "needs_transaction_details": "transaction_clarification",
        "needs_dispute_classification": "classification_question",
        "dispute_classified": "csat_unclear",
    }.get(stage)
    if step is None:
        return web_text(state.locale.language, "conversation_closed", phone=phone)
    return SipRealtimeGateway._message_for(state, step)


def reference_message(state: VoiceCallState, outcome: str, *, phone: str) -> str:
    """The deterministic message for an outcome; also the fallback when the LLM fails."""

    language = state.locale.language
    if outcome in VOICE_TEMPLATE_OUTCOMES:
        return SipRealtimeGateway._message_for(state, outcome)
    if outcome == "transaction_handoff":
        return web_text(language, "handoff", phone=phone)
    if outcome == "transaction_options":
        count = len(state.transaction_candidates)
        key = "transaction_option_single" if count == 1 else "transaction_options"
        return web_text(language, key, count=count)
    if outcome in {"question", "out_of_scope"}:
        return f"{web_text(language, outcome)} {current_step_message(state, phone=phone)}"
    name = state.identity.first_name if state.identity is not None else ""
    return web_text(language, outcome, name=name, phone=phone)


def reply_facts(
    state: VoiceCallState,
    outcome: str,
    *,
    phone: str,
    card_last_four: str | None,
    today: date | None = None,
) -> dict[str, Any]:
    """Authoritative, minimal facts the reply model may mention (no ids beyond the complaint)."""

    transaction = state.current_transaction or state.confirmed_transaction
    classification = state.dispute_classification
    facts: dict[str, Any] = {
        # Without today's date the model guessed wrongly that past years were "in the future".
        "today": (today or date.today()).isoformat(),
        "customer_first_name": state.identity.first_name if state.identity else None,
        "stage": state.stage.value,
        "outcome": outcome,
        "active_filters": (
            criteria.web_filters()
            if isinstance(criteria := state.transaction_criteria, CardPurchaseCriteria)
            else {name: str(value) for name, value in criteria.active_filters()}
        ),
        "next_detail_to_ask": state.pending_transaction_detail,
        "izzy_phone": format_phone(phone),
    }
    if transaction is not None:
        facts["transaction"] = {
            "merchant": transaction.merchant_name,
            "date": transaction.transaction_date.date().isoformat(),
            "amount": transaction.amount,
            "currency": transaction.currency,
            "city": transaction.transaction_city,
            "country": transaction.transaction_country,
            "channel": transaction.channel,
            "category": transaction.transaction_category,
            "card_last_four": card_last_four,
            "confirmed": state.confirmed_transaction is not None,
        }
    if classification is not None:
        facts["classification"] = {
            "allegation": classification.allegation.value,
            "status": classification.status.value,
            "visa_condition_code": classification.visa_condition_code,
        }
    if state.card_security_action is not None:
        facts["card_security_action"] = {
            "status": state.card_security_action.value,
            "card_last_four": state.secured_card_last_four,
        }
    if state.complaint_filing_status is not None:
        facts["complaint"] = {
            "filing_status": state.complaint_filing_status.value,
            "complaint_id": state.complaint_id,
            "status": state.complaint_status,
        }
    return facts


def required_tokens(facts: dict[str, Any]) -> tuple[str, ...]:
    """Identifiers a rephrased reply must keep verbatim; otherwise the reference is sent."""

    tokens: list[str] = []
    complaint = facts.get("complaint") or {}
    if complaint.get("complaint_id"):
        tokens.append(str(complaint["complaint_id"]))
    classification = facts.get("classification") or {}
    if classification.get("visa_condition_code"):
        tokens.append(str(classification["visa_condition_code"]))
    security = facts.get("card_security_action") or {}
    if security.get("card_last_four"):
        tokens.append(str(security["card_last_four"]))
    return tuple(tokens)


LANGUAGE_NAMES = {"en": "English", "es": "Spanish (Latin America)", "pt": "Brazilian Portuguese"}

REPLY_PROMPT = """You are Izzy, Factored Bank's virtual assistant, writing the next message in a \
web chat with an authenticated customer. Reply in {language_name}.

Write 1 to 3 short sentences and ask at most one question. Plain text only, no markdown, no lists.
The REFERENCE message is the correct next step. Rephrase it naturally for a chat (not a phone \
call: never mention keypads, transfers, or staying on the line) and keep every fact and the \
question it asks. Use only facts present in FACTS or REFERENCE; never invent merchants, amounts, \
dates, codes, card digits, or complaint numbers. Complaints are demo records: never say a dispute \
was submitted to Visa or that money will be refunded.
If FACTS.outcome is "question", first answer the customer's question in one or two sentences \
using general, non-binding knowledge about card disputes, then continue with the REFERENCE step.
If FACTS.outcome is "out_of_scope", politely decline and continue with the REFERENCE step.
Today's date is FACTS.today. Never call a date the customer mentions "future", "too old" or \
invalid, and never refuse to help because of a date: the search already used the dates.

FACTS: {facts}
REFERENCE: {reference}"""
