import { ApiError, apiRequest } from "../api.js";
import { requireCustomer } from "../auth.js";
import { formatCurrency, formatDate, getLocale, i18nReady, t, translateValue } from "../i18n.js?v=1";

await i18nReady;

import { renderBottomNavigation } from "../components/bottom-nav.js?v=4";
import { initializeGuidedTour } from "../components/guided-tour.js?v=12";


const page = document.querySelector("#agent-page");
const messages = document.querySelector("#agent-messages");
const composer = document.querySelector("#agent-composer");
const input = document.querySelector("#agent-input");
const sendButton = document.querySelector("#agent-send");
const closedPanel = document.querySelector("#agent-closed");
const newChatButton = document.querySelector("#agent-new-chat");
const callButton = document.querySelector("#agent-call");
const phoneLink = document.querySelector("#agent-phone-link");
const bottomNav = document.querySelector("#bottom-nav");

let sessionId = null;
let busy = false;
let activeOptions = null;


function scrollToLatest() {
    messages.scrollTop = messages.scrollHeight;
    window.scrollTo({ top: document.body.scrollHeight });
}

function addBubble(role, text = "") {
    const bubble = document.createElement("p");
    bubble.className = `agent-bubble agent-bubble-${role}`;
    bubble.textContent = text;
    messages.append(bubble);
    scrollToLatest();
    return bubble;
}

function addTypingBubble() {
    const bubble = addBubble("izzy");
    bubble.classList.add("agent-bubble-typing");
    bubble.setAttribute("aria-label", t("izzy.typing"));
    bubble.innerHTML = "<span></span><span></span><span></span>";
    return bubble;
}

function setComposerEnabled(enabled) {
    input.disabled = !enabled;
    sendButton.disabled = !enabled || !input.value.trim();
    if (enabled) input.focus();
}

function showClosed(text) {
    if (text) closedPanel.querySelector("p").textContent = text;
    closedPanel.hidden = false;
    composer.hidden = true;
}

function setPhone(phoneNumber, phoneDisplay) {
    const href = `tel:${phoneNumber}`;
    callButton.href = href;
    phoneLink.href = href;
    phoneLink.textContent = phoneDisplay;
}

function autoResize() {
    input.style.height = "auto";
    input.style.height = `${Math.min(input.scrollHeight, 128)}px`;
}


// ----------------------------------------------------------------- purchase options

function optionSummary(option) {
    const amount = formatCurrency(option.amount, option.currency);
    return `${option.merchant || t("izzy.unknown_merchant")} · ${amount}`;
}

function disableOptions(selectedId = null) {
    if (!activeOptions) return;
    for (const button of activeOptions.querySelectorAll("button")) {
        button.disabled = true;
        if (selectedId && button.dataset.transactionId === selectedId) {
            button.classList.add("agent-option-selected");
            button.setAttribute("aria-pressed", "true");
        }
    }
    activeOptions = null;
}

function renderOptions(options, { selectedId = null, closed = false } = {}) {
    disableOptions();
    if (!options?.length) return;

    const group = document.createElement("div");
    group.className = "agent-options";
    group.setAttribute("role", "group");
    group.setAttribute("aria-label", t("izzy.options_label"));

    options.forEach((option, index) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "agent-option";
        button.dataset.transactionId = option.transaction_id;

        const number = document.createElement("span");
        number.className = "agent-option-number";
        number.textContent = String(index + 1);

        const body = document.createElement("span");
        body.className = "agent-option-body";

        const title = document.createElement("span");
        title.className = "agent-option-title";
        title.textContent = option.merchant || t("izzy.unknown_merchant");

        const amount = document.createElement("span");
        amount.className = "agent-option-amount";
        amount.textContent = formatCurrency(option.amount, option.currency);

        const place = [option.city, option.country].filter(Boolean).join(", ");
        const meta = document.createElement("span");
        meta.className = "agent-option-meta";
        meta.textContent = [formatDate(option.date), place, translateValue(option.category)]
            .filter(Boolean)
            .join(" · ");

        const card = document.createElement("span");
        card.className = "agent-option-card";
        card.textContent = t("izzy.card_ending", {
            card: translateValue(option.card_type),
            digits: option.card_last_four,
        });

        body.append(title, amount, meta, card);
        button.append(number, body);
        button.addEventListener("click", () => {
            if (busy) return;
            disableOptions(option.transaction_id);
            sendTurn({ selectedTransactionId: option.transaction_id, label: optionSummary(option) });
        });
        group.append(button);
    });

    messages.append(group);
    activeOptions = group;

    if (selectedId || closed) {
        // Already answered (or opened from a purchase): shown as context, not clickable.
        disableOptions(selectedId);
        scrollToLatest();
        return;
    }

    const none = document.createElement("button");
    none.type = "button";
    none.className = "agent-option-none";
    none.textContent = t("izzy.none_of_these");
    none.addEventListener("click", () => {
        if (busy) return;
        disableOptions();
        sendTurn({ rejectOptions: true, label: t("izzy.none_of_these") });
    });
    group.append(none);
    scrollToLatest();
}


// ----------------------------------------------------------------- streaming

function parseEventBlock(block) {
    let name = "message";
    const data = [];
    for (const line of block.split("\n")) {
        if (line.startsWith("event: ")) name = line.slice(7).trim();
        else if (line.startsWith("data: ")) data.push(line.slice(6));
    }
    if (!data.length) return null;
    try {
        return { name, payload: JSON.parse(data.join("\n")) };
    } catch {
        return null;
    }
}

async function readEvents(response, onEvent) {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
        let boundary = buffer.indexOf("\n\n");
        while (boundary !== -1) {
            const event = parseEventBlock(buffer.slice(0, boundary));
            buffer = buffer.slice(boundary + 2);
            if (event) onEvent(event);
            boundary = buffer.indexOf("\n\n");
        }
    }
}


function sessionRequest() {
    const transactionId = new URLSearchParams(window.location.search).get("transaction_id");
    return {
        transaction_id: transactionId || null,
        locale: getLocale(),
    };
}


async function replaceLostSession() {
    const opening = await apiRequest("/izzy/sessions", {
        method: "POST",
        body: JSON.stringify(sessionRequest()),
    });
    sessionId = opening.session_id;
    setPhone(opening.phone_number, opening.phone_display);
}


async function sendTurn({ text = "", selectedTransactionId = null, rejectOptions = false, label }) {
    busy = true;
    setComposerEnabled(false);
    addBubble("customer", label || text);
    const reply = addTypingBubble();
    let replyText = "";
    let closed = false;
    let pendingOptions = null;

    const render = (value, links = []) => {
        reply.classList.remove("agent-bubble-typing");
        reply.removeAttribute("aria-label");
        reply.replaceChildren();
        let remaining = value;
        for (const link of links) {
            const index = remaining.indexOf(link.text);
            if (index < 0) continue;
            reply.append(document.createTextNode(remaining.slice(0, index)));
            const anchor = document.createElement("a");
            anchor.href = link.href;
            anchor.textContent = link.text;
            reply.append(anchor);
            remaining = remaining.slice(index + link.text.length);
        }
        reply.append(document.createTextNode(remaining));
        scrollToLatest();
    };

    try {
        const submit = () => fetch(
            `/api/izzy/sessions/${encodeURIComponent(sessionId)}/messages`,
            {
                method: "POST",
                credentials: "same-origin",
                headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
                body: JSON.stringify({
                    message: text,
                    selected_transaction_id: selectedTransactionId,
                    reject_options: rejectOptions,
                }),
            },
        );
        let response = await submit();

        // A serverless worker can be recycled between two HTTP requests. Re-open the same
        // customer/transaction context once and deliver the message instead of declaring that a
        // chat which was opened seconds ago has expired.
        if (response.status === 404) {
            await replaceLostSession();
            response = await submit();
        }

        if (response.status === 401) {
            window.location.replace("/login");
            return;
        }
        if (response.status === 404) {
            render(t("izzy.session_expired"));
            showClosed(t("izzy.session_expired"));
            return;
        }
        if (!response.ok || !response.body) {
            throw new Error(`Chat request failed with status ${response.status}.`);
        }

        await readEvents(response, ({ name, payload }) => {
            if (name === "delta") {
                replyText += payload.text;
                render(replyText);
            } else if (name === "replace" || name === "error") {
                replyText = payload.text;
                render(replyText);
                if (name === "error") reply.classList.add("agent-bubble-error");
            } else if (name === "options") {
                pendingOptions = payload.options;
            } else if (name === "selected") {
                disableOptions(payload.transaction_id);
            } else if (name === "state") {
                closed = Boolean(payload.closed);
                if (payload.links?.length) render(replyText, payload.links);
                if (payload.stage !== "confirm_transaction") disableOptions();
            }
        });

        if (!replyText) render(t("izzy.unavailable"));
        // Options appear under Izzy's message so the question comes first.
        if (pendingOptions) renderOptions(pendingOptions);
        if (closed) showClosed();
    } catch (error) {
        console.error("Unable to reach Izzy:", error);
        render(t("izzy.unavailable"));
        reply.classList.add("agent-bubble-error");
    } finally {
        busy = false;
        if (!closed && closedPanel.hidden) setComposerEnabled(true);
    }
}


function renderHistory(entries, stage) {
    // A new chat has just the greeting; a resumed chat shows everything said so far.
    const lastOptions = entries.map((entry) => entry.role).lastIndexOf("options");
    entries.forEach((entry, index) => {
        if (entry.role === "options") {
            const active = index === lastOptions && stage === "confirm_transaction";
            renderOptions(entry.options, {
                selectedId: entry.selected,
                closed: entry.closed || !active,
            });
        } else {
            addBubble(entry.role, entry.text);
        }
    });
}


async function openSession() {
    messages.replaceChildren();
    activeOptions = null;
    closedPanel.hidden = true;
    composer.hidden = false;
    const typing = addTypingBubble();
    try {
        const opening = await apiRequest("/izzy/sessions", {
            method: "POST",
            body: JSON.stringify(sessionRequest()),
        });
        sessionId = opening.session_id;
        setPhone(opening.phone_number, opening.phone_display);
        typing.remove();
        renderHistory(opening.messages, opening.stage);
        setComposerEnabled(true);
    } catch (error) {
        if (error instanceof ApiError && error.status === 401) {
            window.location.replace("/login");
            return;
        }
        console.error("Unable to start the Izzy chat:", error);
        typing.remove();
        addBubble("izzy", t("izzy.unavailable")).classList.add("agent-bubble-error");
    }
}


composer.addEventListener("submit", (event) => {
    event.preventDefault();
    const text = input.value.trim();
    if (!text || busy || !sessionId) return;
    input.value = "";
    autoResize();
    sendTurn({ text });
});

input.addEventListener("input", () => {
    autoResize();
    sendButton.disabled = busy || !input.value.trim();
});

input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
        event.preventDefault();
        composer.requestSubmit();
    }
});

newChatButton.addEventListener("click", () => {
    const url = new URL(window.location.href);
    url.searchParams.delete("transaction_id");
    url.searchParams.delete("intent");
    window.history.replaceState({}, "", url);
    openSession();
});


async function initializePage() {
    const customer = await requireCustomer();
    if (!customer) return;
    renderBottomNavigation(bottomNav, "agent");
    page.hidden = false;
    await openSession();
    await initializeGuidedTour();
}


initializePage().catch((error) => {
    console.error("Unable to initialize the Izzy chat:", error);
    window.location.replace("/login");
});
