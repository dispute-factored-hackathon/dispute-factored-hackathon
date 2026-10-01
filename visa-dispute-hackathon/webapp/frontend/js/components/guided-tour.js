import { apiRequest } from "../api.js";

const COPY = {
    controls: {
        activate: "Select the highlighted control to continue.",
        close: "Close tutorial",
        error: "The tour could not save your progress. Try again or reload the page.",
        finish: "Finish",
        next: "Next",
        previous: "Previous",
        progress: (current, total) => `Step ${current} of ${total}`,
        skip: "Skip tour",
    },
    steps: {
        welcome: [
            "Welcome to Factored Bank",
            "This interactive tour will guide you through the real controls used to review and dispute a card transaction.",
        ],
        "cards-link": [
            "Start with your cards",
            "Select Cards to review the cards connected to this demo account.",
        ],
        cards: [
            "Your demo cards",
            "This page shows each card and its status. You can block a card here if you believe it is compromised.",
        ],
        "transactions-link": [
            "Review account activity",
            "Select Transactions to inspect purchases and identify a payment you want to report.",
        ],
        transactions: [
            "Choose a transaction",
            "Select a transaction to review its merchant, amount, date, channel, and location.",
        ],
        "report-transaction": [
            "Report a payment problem",
            "Select this action to send the transaction to Izzy as context for the dispute conversation.",
        ],
        izzy: [
            "Meet Izzy",
            "Izzy helps customers understand payment problems and start card disputes by chat or telephone.",
        ],
        "complaints-link": [
            "Follow existing disputes",
            "Select Complaints to see disputes that have already been opened.",
        ],
        complaints: [
            "Track dispute progress",
            "Complaints shows the status, claimed amount, and latest state of each dispute. This demo account may not have one yet.",
        ],
        "profile-link": [
            "Review your profile",
            "Select Profile to review the customer information used by this demo.",
        ],
        profile: [
            "Keep your information current",
            "Contact and voice preferences can be changed here. The Factored ID remains read-only.",
        ],
        finish: [
            "You are ready",
            "You can now explore Factored Bank on your own. Replay this tour at any time from the Home page.",
        ],
    },
};

const STEPS = [
    { id: "welcome", route: "/home" },
    {
        id: "cards-link",
        route: "/home",
        target: "[data-tour='cards-link']",
        action: "activate",
    },
    {
        id: "cards",
        route: "/cards",
        target: ".bank-card-container",
        allowMissingTarget: true,
    },
    {
        id: "transactions-link",
        route: "/home",
        target: "[data-tour='transactions-link']",
        action: "activate",
    },
    {
        id: "transactions",
        route: "/transactions",
        target: ".transaction-item",
        action: "activate",
        allowMissingTarget: true,
    },
    {
        id: "report-transaction",
        route: transactionDetailRoute,
        target: "#report-button",
        action: "activate",
    },
    { id: "izzy", route: "/agent" },
    {
        id: "complaints-link",
        route: "/home",
        target: "[data-tour='complaints-link']",
        action: "activate",
    },
    {
        id: "complaints",
        route: "/complaints",
        target: ".complaint-item",
        allowMissingTarget: true,
    },
    {
        id: "profile-link",
        route: "/home",
        target: "[data-tour='profile-link']",
        action: "activate",
    },
    { id: "profile", route: "/profile" },
    { id: "finish", route: "/home" },
];

let active = false;
let currentIndex = 0;
let layer = null;
let lastFocused = null;
let targetElement = null;
let targetContext = null;
let targetActivationHandler = null;
let repositionHandler = null;
let transitioning = false;

async function transactionDetailRoute() {
    const transactions = await apiRequest("/transactions", { method: "GET" });
    const first = transactions[0];
    return first ? `/transactions/${encodeURIComponent(first.transaction_id)}` : null;
}

async function routeFor(step) {
    return typeof step.route === "function" ? step.route() : step.route;
}

function pathMatches(route) {
    return route !== null && window.location.pathname === route;
}

function withTourContinuation(destination) {
    const url = new URL(destination, window.location.origin);
    url.searchParams.set("tour", "continue");
    return `${url.pathname}${url.search}${url.hash}`;
}

function waitForTarget(selector, timeout = 3000) {
    return new Promise((resolve) => {
        const started = performance.now();
        function check() {
            const target = document.querySelector(selector);
            if (target && !target.hidden && target.getClientRects().length > 0) {
                resolve(target);
                return;
            }
            if (performance.now() - started >= timeout) {
                resolve(null);
                return;
            }
            requestAnimationFrame(check);
        }
        check();
    });
}

function emitMetric(name, detail = {}) {
    window.dispatchEvent(new CustomEvent("factored:tour-metric", {
        detail: { name, step_id: STEPS[currentIndex]?.id, ...detail },
    }));
}

function createLayer() {
    const container = document.createElement("div");
    container.className = "guided-tour";
    container.innerHTML = `
        <div class="guided-tour-backdrop" aria-hidden="true"></div>
        <div class="guided-tour-spotlight" aria-hidden="true"></div>
        <section class="guided-tour-tooltip" role="dialog" aria-labelledby="guided-tour-title" aria-describedby="guided-tour-body">
            <div class="guided-tour-topline">
                <span class="guided-tour-progress"></span>
                <button class="guided-tour-close" type="button"></button>
            </div>
            <h2 id="guided-tour-title"></h2>
            <p id="guided-tour-body"></p>
            <p class="guided-tour-instruction" hidden></p>
            <p class="guided-tour-error" role="alert" hidden></p>
            <div class="guided-tour-actions">
                <button class="button button-secondary guided-tour-previous" type="button"></button>
                <button class="guided-tour-skip" type="button"></button>
                <button class="button button-primary guided-tour-next" type="button"></button>
            </div>
        </section>`;
    document.body.append(container);
    return container;
}

function focusableControls() {
    const controls = [...layer.querySelectorAll("button:not([disabled]):not([hidden])")];
    if (STEPS[currentIndex]?.action === "activate" && targetElement) {
        return [targetElement, ...controls];
    }
    return controls;
}

function trapFocus(event) {
    if (event.key === "Escape") {
        event.preventDefault();
        handleAction(() => skipTour("escape"));
        return;
    }
    if (event.key !== "Tab") return;
    const controls = focusableControls();
    if (controls.length === 0) return;
    const first = controls[0];
    const last = controls.at(-1);
    if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
    }
}

function setControlsDisabled(disabled) {
    for (const button of layer?.querySelectorAll("button") || []) {
        button.disabled = disabled;
    }
    targetElement?.classList.toggle("guided-tour-target-busy", disabled);
    if (targetElement && disabled) targetElement.setAttribute("aria-disabled", "true");
    else targetElement?.removeAttribute("aria-disabled");
}

async function handleAction(action) {
    if (transitioning) return;
    transitioning = true;
    setControlsDisabled(true);
    try {
        await action();
    } catch (error) {
        console.error("Unable to update guided tour:", error);
        const message = layer?.querySelector(".guided-tour-error");
        if (message) {
            message.textContent = COPY.controls.error;
            message.hidden = false;
        }
        setControlsDisabled(false);
        const previous = layer?.querySelector(".guided-tour-previous");
        if (previous) previous.disabled = currentIndex === 0;
        layer?.querySelector(".guided-tour-next")?.focus();
    } finally {
        transitioning = false;
    }
}

function clearTarget() {
    if (targetElement && targetActivationHandler) {
        targetElement.removeEventListener("click", targetActivationHandler, true);
    }
    targetElement?.classList.remove("guided-tour-target", "guided-tour-target-busy");
    targetElement?.removeAttribute("aria-disabled");
    targetContext?.classList.remove("guided-tour-target-context");
    targetElement = null;
    targetContext = null;
    targetActivationHandler = null;
}

function setTarget(target, interactive) {
    clearTarget();
    targetElement = target;
    if (!target) return;
    target.classList.add("guided-tour-target");
    targetContext = target.closest(".app-header, .bottom-nav");
    targetContext?.classList.add("guided-tour-target-context");
    if (!interactive) return;
    targetActivationHandler = (event) => {
        event.preventDefault();
        event.stopPropagation();
        handleAction(() => activateTarget(target));
    };
    target.addEventListener("click", targetActivationHandler, true);
}

function tooltipPlacement(rect, tooltipRect) {
    const gap = 18;
    const margin = 16;
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;
    const spaces = {
        bottom: viewportHeight - rect.bottom - gap - margin,
        top: rect.top - gap - margin,
        right: viewportWidth - rect.right - gap - margin,
        left: rect.left - gap - margin,
    };
    const candidates = [
        {
            side: "bottom",
            available: spaces.bottom,
            fits: spaces.bottom >= tooltipRect.height,
            top: rect.bottom + gap,
            left: rect.left + rect.width / 2 - tooltipRect.width / 2,
        },
        {
            side: "top",
            available: spaces.top,
            fits: spaces.top >= tooltipRect.height,
            top: rect.top - gap - tooltipRect.height,
            left: rect.left + rect.width / 2 - tooltipRect.width / 2,
        },
        {
            side: "right",
            available: spaces.right,
            fits: spaces.right >= tooltipRect.width,
            top: rect.top + rect.height / 2 - tooltipRect.height / 2,
            left: rect.right + gap,
        },
        {
            side: "left",
            available: spaces.left,
            fits: spaces.left >= tooltipRect.width,
            top: rect.top + rect.height / 2 - tooltipRect.height / 2,
            left: rect.left - gap - tooltipRect.width,
        },
    ];
    return candidates.find((candidate) => candidate.fits)
        || candidates.sort((a, b) => spaces[b.side] - spaces[a.side])[0];
}

function positionTour() {
    if (!layer) return;
    const spotlight = layer.querySelector(".guided-tour-spotlight");
    const tooltip = layer.querySelector(".guided-tour-tooltip");
    if (!targetElement) {
        layer.classList.add("guided-tour-no-target");
        spotlight.hidden = true;
        tooltip.removeAttribute("style");
        return;
    }

    layer.classList.remove("guided-tour-no-target");
    spotlight.hidden = false;
    const rect = targetElement.getBoundingClientRect();
    const padding = 8;
    spotlight.style.setProperty("--tour-left", `${Math.max(8, rect.left - padding)}px`);
    spotlight.style.setProperty("--tour-top", `${Math.max(8, rect.top - padding)}px`);
    spotlight.style.setProperty("--tour-width", `${Math.min(window.innerWidth - 16, rect.width + padding * 2)}px`);
    spotlight.style.setProperty("--tour-height", `${Math.min(window.innerHeight - 16, rect.height + padding * 2)}px`);

    tooltip.style.width = `${Math.min(380, window.innerWidth - 32)}px`;
    tooltip.style.maxHeight = `${Math.max(120, window.innerHeight - 32)}px`;
    let tooltipRect = tooltip.getBoundingClientRect();
    let placement = tooltipPlacement(rect, tooltipRect);
    if (!placement.fits && ["top", "bottom"].includes(placement.side)) {
        tooltip.style.maxHeight = `${Math.max(96, placement.available)}px`;
        tooltipRect = tooltip.getBoundingClientRect();
        placement = tooltipPlacement(rect, tooltipRect);
    }
    const left = Math.min(
        window.innerWidth - tooltipRect.width - 16,
        Math.max(16, placement.left),
    );
    const top = Math.min(
        window.innerHeight - tooltipRect.height - 16,
        Math.max(16, placement.top),
    );
    tooltip.style.left = `${left}px`;
    tooltip.style.top = `${top}px`;
    tooltip.style.right = "auto";
    tooltip.style.bottom = "auto";
    tooltip.dataset.placement = placement.side;
}

function removeLayer() {
    window.removeEventListener("resize", repositionHandler);
    window.removeEventListener("scroll", repositionHandler, true);
    document.removeEventListener("keydown", trapFocus);
    document.body.classList.remove("guided-tour-active");
    clearTarget();
    layer?.remove();
    layer = null;
    active = false;
    lastFocused?.focus?.();
}

async function saveProgress(status, lastCompletedStep) {
    return apiRequest("/onboarding/tour", {
        method: "PATCH",
        body: JSON.stringify({ status, last_completed_step: lastCompletedStep }),
    });
}

async function skipMissingStep() {
    emitMetric("target_missing");
    await saveProgress("in_progress", STEPS[currentIndex].id);
    currentIndex += 1;
    if (currentIndex >= STEPS.length) await finishTour();
    else await showCurrentStep();
}

async function showCurrentStep() {
    const step = STEPS[currentIndex];
    if (!step) return;
    const route = await routeFor(step);
    if (!route) {
        await skipMissingStep();
        return;
    }
    if (!pathMatches(route)) {
        window.location.assign(withTourContinuation(route));
        return;
    }

    let target = null;
    if (step.target) {
        target = await waitForTarget(step.target);
        if (!target && !step.allowMissingTarget) {
            await skipMissingStep();
            return;
        }
    }
    if (target) target.scrollIntoView({ block: "center", behavior: "auto" });
    setTarget(target, step.action === "activate");
    if (!layer) layer = createLayer();

    const [title, body] = COPY.steps[step.id];
    layer.querySelector(".guided-tour-progress").textContent = COPY.controls.progress(currentIndex + 1, STEPS.length);
    layer.querySelector(".guided-tour-close").textContent = "×";
    layer.querySelector(".guided-tour-close").setAttribute("aria-label", COPY.controls.close);
    layer.querySelector("#guided-tour-title").textContent = title;
    layer.querySelector("#guided-tour-body").textContent = body;
    layer.querySelector(".guided-tour-error").hidden = true;
    const instruction = layer.querySelector(".guided-tour-instruction");
    instruction.textContent = COPY.controls.activate;
    instruction.hidden = step.action !== "activate" || !target;
    layer.classList.toggle(
        "guided-tour-action-step",
        step.action === "activate" && Boolean(target),
    );

    setControlsDisabled(false);
    const previous = layer.querySelector(".guided-tour-previous");
    previous.textContent = COPY.controls.previous;
    previous.disabled = currentIndex === 0;
    const skip = layer.querySelector(".guided-tour-skip");
    skip.textContent = COPY.controls.skip;
    const next = layer.querySelector(".guided-tour-next");
    next.textContent = currentIndex === STEPS.length - 1 ? COPY.controls.finish : COPY.controls.next;
    next.hidden = step.action === "activate" && Boolean(target);
    previous.onclick = () => handleAction(previousStep);
    skip.onclick = () => handleAction(() => skipTour("button"));
    layer.querySelector(".guided-tour-close").onclick = () => handleAction(() => skipTour("close"));
    next.onclick = () => handleAction(nextStep);
    positionTour();
    if (step.action === "activate" && target) target.focus();
    else next.focus();
    emitMetric("step_viewed", { presentation: target ? "targeted" : "untargeted" });
}

async function activateTarget(target) {
    const destination = target.getAttribute("href");
    const completedId = STEPS[currentIndex].id;
    emitMetric("target_activated");
    await saveProgress("in_progress", completedId);
    currentIndex += 1;
    if (destination) {
        window.location.assign(withTourContinuation(destination));
        return;
    }
    await showCurrentStep();
}

async function nextStep() {
    const completedId = STEPS[currentIndex].id;
    if (currentIndex === STEPS.length - 1) {
        await finishTour();
        return;
    }
    await saveProgress("in_progress", completedId);
    currentIndex += 1;
    await showCurrentStep();
}

async function previousStep() {
    if (currentIndex === 0) return;
    currentIndex -= 1;
    const previousCompleted = currentIndex > 0 ? STEPS[currentIndex - 1].id : null;
    await saveProgress("in_progress", previousCompleted);
    await showCurrentStep();
}

async function finishTour() {
    await saveProgress("completed", STEPS.at(-1).id);
    emitMetric("completed");
    removeLayer();
}

async function skipTour(source) {
    const lastCompleted = currentIndex > 0 ? STEPS[currentIndex - 1].id : null;
    await saveProgress("skipped", lastCompleted);
    emitMetric("skipped", { source });
    removeLayer();
}

function indexAfter(lastCompletedStep) {
    if (!lastCompletedStep) return 0;
    const index = STEPS.findIndex((step) => step.id === lastCompletedStep);
    return index < 0 ? 0 : Math.min(index + 1, STEPS.length - 1);
}

async function runGuidedTour() {
    if (active) return;
    const parameters = new URLSearchParams(window.location.search);
    const restart = parameters.get("tour") === "start";
    const state = restart
        ? await saveProgress("in_progress", null)
        : await apiRequest("/onboarding/tour", { method: "GET" });

    if (parameters.has("tour")) {
        parameters.delete("tour");
        const remainingQuery = parameters.toString();
        window.history.replaceState(
            {},
            "",
            `${window.location.pathname}${remainingQuery ? `?${remainingQuery}` : ""}${window.location.hash}`,
        );
    }
    const shouldRun = restart
        || state.status === "in_progress"
        || (state.should_offer && window.location.pathname === "/home");
    if (!shouldRun) return;

    active = true;
    currentIndex = restart ? 0 : indexAfter(state.last_completed_step);
    lastFocused = document.activeElement;
    document.body.classList.add("guided-tour-active");
    repositionHandler = () => positionTour();
    window.addEventListener("resize", repositionHandler);
    window.addEventListener("scroll", repositionHandler, true);
    document.addEventListener("keydown", trapFocus);
    if (state.status !== "in_progress") {
        await saveProgress("in_progress", null);
        emitMetric("started");
    }
    await showCurrentStep();
}

export async function initializeGuidedTour() {
    try {
        await runGuidedTour();
    } catch (error) {
        console.error("Unable to initialize guided tour:", error);
        emitMetric("initialization_failed");
        removeLayer();
    }
}
