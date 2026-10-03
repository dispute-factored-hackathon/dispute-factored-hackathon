import { ApiError, apiRequest } from "../api.js";
import { requireCustomer } from "../auth.js";
import { getLocale, i18nReady, t } from "../i18n.js?v=1";

await i18nReady;

import { renderBottomNavigation } from "../components/bottom-nav.js?v=4";
import { initializeGuidedTour } from "../components/guided-tour.js?v=7";


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


async function sendMessage(text) {
    busy = true;
    setComposerEnabled(false);
    addBubble("customer", text);
    const reply = addTypingBubble();
    let replyText = "";
    let closed = false;

    const render = (value) => {
        reply.classList.remove("agent-bubble-typing");
        reply.removeAttribute("aria-label");
        reply.textContent = value;
        scrollToLatest();
    };

    try {
        const response = await fetch(`/api/izzy/sessions/${encodeURIComponent(sessionId)}/messages`, {
            method: "POST",
            credentials: "same-origin",
            headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
            body: JSON.stringify({ message: text }),
        });

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
            } else if (name === "state") {
                closed = Boolean(payload.closed);
            }
        });

        if (!replyText) render(t("izzy.unavailable"));
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


async function openSession() {
    messages.replaceChildren();
    closedPanel.hidden = true;
    composer.hidden = false;
    const transactionId = new URLSearchParams(window.location.search).get("transaction_id");
    const typing = addTypingBubble();
    try {
        const opening = await apiRequest("/izzy/sessions", {
            method: "POST",
            body: JSON.stringify({
                transaction_id: transactionId || null,
                locale: getLocale(),
            }),
        });
        sessionId = opening.session_id;
        setPhone(opening.phone_number, opening.phone_display);
        typing.remove();
        addBubble("izzy", opening.message);
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
    sendMessage(text);
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
