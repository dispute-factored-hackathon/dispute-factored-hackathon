import { apiRequest } from "../api.js";

const COPY = {
    en: {
        controls: {
            close: "Close tutorial",
            error: "The tour could not save your progress. Your banking session is still available. Try again or reload the page.",
            finish: "Finish",
            next: "Next",
            previous: "Previous",
            progress: (current, total) => `Step ${current} of ${total}`,
            skip: "Skip tour",
        },
        steps: {
            welcome: ["Welcome to Factored Bank", "This short tour highlights the real controls you will use in the demo."],
            menu: ["Your banking menu", "Use this area to reach cards, transactions, complaints, and your profile."],
            "cards-link": ["Start with your cards", "Open Cards to see which demo cards are active or blocked."],
            cards: ["Your demo cards", "Card details and status appear here. A compromised card can be blocked from this page."],
            "transactions-link": ["Review account activity", "Transactions is where you inspect purchases and find something you want to report."],
            transactions: ["Choose a transaction", "Open a transaction to review its merchant, amount, date, channel, and location."],
            "report-transaction": ["Report a payment problem", "This action sends the selected transaction to Izzy as context for the dispute conversation."],
            izzy: ["Meet Izzy", "Izzy helps you understand a payment problem and start a card dispute by chat or telephone."],
            complaints: ["Follow your disputes", "Complaints shows cases you already opened, including their status and resolution."],
            profile: ["Keep your profile current", "Update your contact and voice preferences here. Your Factored ID stays protected from editing."],
            replay: ["Replay whenever you need", "Use this control to restart the guided tour from the beginning."],
        },
    },
    pt: {
        controls: {
            close: "Fechar tutorial",
            error: "O tour não conseguiu salvar seu progresso. Sua sessão bancária continua disponível. Tente novamente ou recarregue a página.",
            finish: "Concluir",
            next: "Próximo",
            previous: "Anterior",
            progress: (current, total) => `Etapa ${current} de ${total}`,
            skip: "Pular tutorial",
        },
        steps: {
            welcome: ["Boas-vindas ao Factored Bank", "Este tour curto destaca os controles reais que você usará na demonstração."],
            menu: ["Seu menu bancário", "Use esta área para acessar cartões, transações, contestações e seu perfil."],
            "cards-link": ["Comece pelos cartões", "Abra Cartões para ver quais cartões de demonstração estão ativos ou bloqueados."],
            cards: ["Seus cartões de demonstração", "Os dados e o status dos cartões aparecem aqui. Um cartão comprometido pode ser bloqueado nesta página."],
            "transactions-link": ["Revise as movimentações", "Em Transações você confere compras e encontra algo que deseja contestar."],
            transactions: ["Escolha uma transação", "Abra uma transação para conferir estabelecimento, valor, data, canal e localização."],
            "report-transaction": ["Conteste um problema de pagamento", "Esta ação envia a transação selecionada para Izzy como contexto da conversa de contestação."],
            izzy: ["Conheça Izzy", "Izzy ajuda a entender um problema de pagamento e iniciar uma contestação por chat ou telefone."],
            complaints: ["Acompanhe suas contestações", "Contestações mostra casos já abertos, incluindo status e resolução."],
            profile: ["Mantenha seu perfil atualizado", "Atualize seus dados de contato e preferências de voz. Seu Factored ID não pode ser editado."],
            replay: ["Reveja quando precisar", "Use este controle para reiniciar o tour guiado desde o começo."],
        },
    },
    es: {
        controls: {
            close: "Cerrar tutorial",
            error: "El recorrido no pudo guardar tu progreso. Tu sesión bancaria sigue disponible. Inténtalo de nuevo o recarga la página.",
            finish: "Finalizar",
            next: "Siguiente",
            previous: "Anterior",
            progress: (current, total) => `Paso ${current} de ${total}`,
            skip: "Omitir tutorial",
        },
        steps: {
            welcome: ["Bienvenido a Factored Bank", "Este breve recorrido destaca los controles reales que usarás en la demostración."],
            menu: ["Tu menú bancario", "Usa esta área para acceder a tarjetas, transacciones, reclamos y tu perfil."],
            "cards-link": ["Comienza con tus tarjetas", "Abre Tarjetas para ver cuáles tarjetas de demostración están activas o bloqueadas."],
            cards: ["Tus tarjetas de demostración", "Aquí aparecen los datos y el estado de las tarjetas. Puedes bloquear una tarjeta comprometida desde esta página."],
            "transactions-link": ["Revisa los movimientos", "En Transacciones puedes revisar compras y encontrar algo que quieras reclamar."],
            transactions: ["Elige una transacción", "Abre una transacción para revisar comercio, monto, fecha, canal y ubicación."],
            "report-transaction": ["Reporta un problema de pago", "Esta acción envía la transacción seleccionada a Izzy como contexto para el reclamo."],
            izzy: ["Conoce a Izzy", "Izzy te ayuda a entender un problema de pago e iniciar un reclamo por chat o teléfono."],
            complaints: ["Sigue tus reclamos", "Reclamos muestra los casos que ya abriste, junto con su estado y resolución."],
            profile: ["Mantén tu perfil actualizado", "Actualiza tus datos de contacto y preferencias de voz. Tu Factored ID no se puede editar."],
            replay: ["Repásalo cuando quieras", "Usa este control para reiniciar el recorrido guiado desde el principio."],
        },
    },
};

const STEPS = [
    { id: "welcome", route: "/home", target: ".welcome" },
    { id: "menu", route: "/home", target: ".banking-section" },
    { id: "cards-link", route: "/home", target: "[data-tour='cards-link']" },
    { id: "cards", route: "/cards", target: "#cards-list" },
    { id: "transactions-link", route: "/home", target: "[data-tour='transactions-link']" },
    { id: "transactions", route: "/transactions", target: "#transactions-list" },
    { id: "report-transaction", route: transactionDetailRoute, target: "#report-button" },
    { id: "izzy", route: "/home", target: ".izzy-hero" },
    { id: "complaints", route: "/complaints", target: ".complaints-content" },
    { id: "profile", route: "/profile", target: ".profile-content" },
    { id: "replay", route: "/home", target: ".tutorial-replay" },
];

let active = false;
let currentIndex = 0;
let customerLocale = "en";
let layer = null;
let lastFocused = null;
let targetElement = null;
let repositionHandler = null;

function languageForAccent(accent) {
    if (accent === "portuguese") return "pt";
    if (accent?.includes("spanish")) return "es";
    return "en";
}

function copy() {
    return COPY[customerLocale] || COPY.en;
}

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
        <section class="guided-tour-tooltip" role="dialog" aria-modal="true" aria-labelledby="guided-tour-title" aria-describedby="guided-tour-body">
            <div class="guided-tour-topline">
                <span class="guided-tour-progress"></span>
                <button class="guided-tour-close" type="button"></button>
            </div>
            <h2 id="guided-tour-title"></h2>
            <p id="guided-tour-body"></p>
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
    return [...layer.querySelectorAll("button:not([disabled])")];
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
}

async function handleAction(action) {
    setControlsDisabled(true);
    try {
        await action();
    } catch (error) {
        console.error("Unable to update guided tour:", error);
        const message = layer?.querySelector(".guided-tour-error");
        if (message) {
            message.textContent = copy().controls.error;
            message.hidden = false;
        }
        setControlsDisabled(false);
        const previous = layer?.querySelector(".guided-tour-previous");
        if (previous) previous.disabled = currentIndex === 0;
        layer?.querySelector(".guided-tour-next")?.focus();
    }
}

function positionTour() {
    if (!targetElement || !layer) return;
    const rect = targetElement.getBoundingClientRect();
    const spotlight = layer.querySelector(".guided-tour-spotlight");
    const tooltip = layer.querySelector(".guided-tour-tooltip");
    const padding = 8;
    spotlight.style.setProperty("--tour-left", `${Math.max(8, rect.left - padding)}px`);
    spotlight.style.setProperty("--tour-top", `${Math.max(8, rect.top - padding)}px`);
    spotlight.style.setProperty("--tour-width", `${Math.min(window.innerWidth - 16, rect.width + padding * 2)}px`);
    spotlight.style.setProperty("--tour-height", `${Math.min(window.innerHeight - 16, rect.height + padding * 2)}px`);

    if (window.innerWidth < 700) {
        tooltip.removeAttribute("style");
        return;
    }
    const tooltipWidth = Math.min(380, window.innerWidth - 32);
    const top = rect.bottom + 18 + 260 <= window.innerHeight
        ? rect.bottom + 18
        : Math.max(16, rect.top - 278);
    const left = Math.min(
        window.innerWidth - tooltipWidth - 16,
        Math.max(16, rect.left + rect.width / 2 - tooltipWidth / 2),
    );
    tooltip.style.width = `${tooltipWidth}px`;
    tooltip.style.left = `${left}px`;
    tooltip.style.top = `${top}px`;
    tooltip.style.right = "auto";
    tooltip.style.bottom = "auto";
}

function removeLayer() {
    window.removeEventListener("resize", repositionHandler);
    window.removeEventListener("scroll", repositionHandler, true);
    document.removeEventListener("keydown", trapFocus);
    document.body.classList.remove("guided-tour-active");
    layer?.remove();
    layer = null;
    targetElement = null;
    active = false;
    lastFocused?.focus?.();
}

async function saveProgress(status, lastCompletedStep) {
    return apiRequest("/onboarding/tour", {
        method: "PATCH",
        body: JSON.stringify({
            status,
            last_completed_step: lastCompletedStep,
        }),
    });
}

async function skipMissingStep() {
    emitMetric("target_missing");
    await saveProgress("in_progress", STEPS[currentIndex].id);
    currentIndex += 1;
    if (currentIndex >= STEPS.length) {
        await finishTour();
        return;
    }
    await showCurrentStep();
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
        window.location.assign(`${route}?tour=continue`);
        return;
    }
    const target = await waitForTarget(step.target);
    if (!target) {
        await skipMissingStep();
        return;
    }
    target.scrollIntoView({ block: "center", behavior: "auto" });
    targetElement = target;
    if (!layer) layer = createLayer();
    const texts = copy();
    const [title, body] = texts.steps[step.id];
    layer.querySelector(".guided-tour-progress").textContent = texts.controls.progress(currentIndex + 1, STEPS.length);
    layer.querySelector(".guided-tour-close").textContent = "×";
    layer.querySelector(".guided-tour-close").setAttribute("aria-label", texts.controls.close);
    layer.querySelector("#guided-tour-title").textContent = title;
    layer.querySelector("#guided-tour-body").textContent = body;
    layer.querySelector(".guided-tour-error").hidden = true;
    setControlsDisabled(false);
    const previous = layer.querySelector(".guided-tour-previous");
    previous.textContent = texts.controls.previous;
    previous.disabled = currentIndex === 0;
    const skip = layer.querySelector(".guided-tour-skip");
    skip.textContent = texts.controls.skip;
    const next = layer.querySelector(".guided-tour-next");
    next.textContent = currentIndex === STEPS.length - 1 ? texts.controls.finish : texts.controls.next;
    previous.onclick = () => handleAction(previousStep);
    skip.onclick = () => handleAction(() => skipTour("button"));
    layer.querySelector(".guided-tour-close").onclick = () => handleAction(() => skipTour("close"));
    next.onclick = () => handleAction(nextStep);
    positionTour();
    next.focus();
    emitMetric("step_viewed");
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

async function runGuidedTour(customer) {
    if (active) return;
    const parameters = new URLSearchParams(window.location.search);
    const restart = parameters.get("tour") === "start";
    const state = restart
        ? await saveProgress("in_progress", null)
        : await apiRequest("/onboarding/tour", { method: "GET" });

    if (restart) {
        window.history.replaceState({}, "", window.location.pathname);
    }
    const shouldRun = restart
        || state.status === "in_progress"
        || (state.should_offer && window.location.pathname === "/home");
    if (!shouldRun) return;

    active = true;
    customerLocale = languageForAccent(customer.preferred_accent);
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

export async function initializeGuidedTour(customer) {
    try {
        await runGuidedTour(customer);
    } catch (error) {
        console.error("Unable to initialize guided tour:", error);
        emitMetric("initialization_failed");
        removeLayer();
    }
}
