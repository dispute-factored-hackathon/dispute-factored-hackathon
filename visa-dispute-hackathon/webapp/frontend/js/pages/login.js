import { ApiError, apiRequest } from "../api.js";
import { getCurrentCustomer } from "../auth.js";

const form = document.querySelector("#login-form");
const searchInput = document.querySelector("#customer-search");
const selectionInput = document.querySelector("#customer-selection");
const optionsList = document.querySelector("#customer-options");
const customerPanel = document.querySelector("#customer-login-panel");
const factoredIdPanel = document.querySelector("#factored-id-login-panel");
const factoredIdInput = document.querySelector("#factored-id");
const methodButtons = [...document.querySelectorAll("[data-method]")];
const loginButton = document.querySelector("#login-button");
const loginError = document.querySelector("#login-error");

let options = [];
let activeIndex = -1;
let searchTimer = null;
let searchController = null;
let loginMethod = "customer";
const startedAt = performance.now();

function emitMetric(name, detail = {}) {
    window.dispatchEvent(new CustomEvent("factored:demo-login-metric", {
        detail: { name, ...detail },
    }));
}

function showError(message) {
    loginError.textContent = message;
    loginError.hidden = false;
}

function clearError() {
    loginError.textContent = "";
    loginError.hidden = true;
}

function setSubmitting(isSubmitting) {
    loginButton.disabled = isSubmitting;
    if (isSubmitting) {
        loginButton.textContent = loginMethod === "customer" ? "Entering demo..." : "Signing in...";
        return;
    }
    loginButton.textContent = loginMethod === "customer" ? "Enter demo" : "Sign in";
}

function setLoginMethod(method, { focus = false } = {}) {
    loginMethod = method;
    const customerSelected = method === "customer";
    customerPanel.hidden = !customerSelected;
    factoredIdPanel.hidden = customerSelected;
    closeOptions();
    clearError();
    methodButtons.forEach((button) => {
        const selected = button.dataset.method === method;
        button.classList.toggle("active", selected);
        button.setAttribute("aria-selected", String(selected));
        button.tabIndex = selected ? 0 : -1;
    });
    loginButton.textContent = customerSelected ? "Enter demo" : "Sign in";
    if (focus) {
        (customerSelected ? searchInput : factoredIdInput).focus();
    }
    emitMetric("login_method_selected", { method });
}

function redirectCustomer(customer) {
    localStorage.setItem("factored_locale", customer.locale);
    document.documentElement.lang = customer.locale;
    window.location.replace(
        customer.onboarding_completed === false ? "/onboarding" : "/home",
    );
}

function closeOptions() {
    optionsList.hidden = true;
    searchInput.setAttribute("aria-expanded", "false");
    searchInput.setAttribute("aria-activedescendant", "");
    activeIndex = -1;
}

function setActiveOption(index) {
    if (options.length === 0) return;
    activeIndex = (index + options.length) % options.length;
    const elements = [...optionsList.querySelectorAll("[role='option']")];
    elements.forEach((element, elementIndex) => {
        const active = elementIndex === activeIndex;
        element.classList.toggle("active", active);
        element.setAttribute("aria-selected", String(active));
    });
    const activeElement = elements[activeIndex];
    searchInput.setAttribute("aria-activedescendant", activeElement.id);
    activeElement.scrollIntoView({ block: "nearest" });
}

function chooseOption(option) {
    searchInput.value = option.full_name;
    selectionInput.value = option.selection;
    clearError();
    closeOptions();
    emitMetric("customer_selected", { result_count: options.length });
}

function renderOptions() {
    optionsList.replaceChildren();
    if (options.length === 0) {
        const empty = document.createElement("p");
        empty.className = "customer-options-empty";
        empty.textContent = "No demo customers match that name.";
        optionsList.append(empty);
        optionsList.hidden = false;
        searchInput.setAttribute("aria-expanded", "true");
        emitMetric("search_no_results");
        return;
    }

    options.forEach((option, index) => {
        const button = document.createElement("button");
        button.type = "button";
        button.id = `customer-option-${index}`;
        button.className = "customer-option";
        button.setAttribute("role", "option");
        button.setAttribute("aria-selected", "false");
        button.innerHTML = `
            <span class="customer-option-name"></span>
            <span class="customer-option-detail"></span>`;
        button.querySelector(".customer-option-name").textContent = option.full_name;
        button.querySelector(".customer-option-detail").textContent = option.disambiguator;
        button.addEventListener("mousedown", (event) => event.preventDefault());
        button.addEventListener("click", () => chooseOption(option));
        optionsList.append(button);
    });
    optionsList.hidden = false;
    searchInput.setAttribute("aria-expanded", "true");
}

async function searchCustomers() {
    searchController?.abort();
    searchController = new AbortController();
    const query = searchInput.value.trim();
    try {
        const response = await apiRequest(
            `/auth/demo-customers?q=${encodeURIComponent(query)}`,
            { method: "GET", signal: searchController.signal },
        );
        options = response.options;
        activeIndex = -1;
        renderOptions();
        emitMetric("search_completed", { result_count: options.length });
    } catch (error) {
        if (error.name === "AbortError") return;
        console.error("Unable to search demo customers:", error);
        closeOptions();
        showError("We could not load demo customers. Please try again.");
    }
}

function scheduleSearch() {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(searchCustomers, 150);
}

async function submitLogin(event) {
    event.preventDefault();
    clearError();
    if (loginMethod === "customer" && !selectionInput.value) {
        showError("Search for a customer and choose one of the demo profiles.");
        searchInput.focus();
        emitMetric("login_failure", { reason: "no_selection" });
        return;
    }

    const factoredId = factoredIdInput.value.replace(/\D/g, "").slice(0, 6);
    factoredIdInput.value = factoredId;
    if (loginMethod === "factored-id" && factoredId.length !== 6) {
        showError("Enter your six-digit Factored ID.");
        factoredIdInput.focus();
        emitMetric("login_failure", { reason: "invalid_factored_id" });
        return;
    }

    setSubmitting(true);
    try {
        const endpoint = loginMethod === "customer" ? "/auth/demo-login" : "/auth/login";
        const payload = loginMethod === "customer"
            ? { selection: selectionInput.value }
            : { factored_id: factoredId };
        const response = await apiRequest(endpoint, {
            method: "POST",
            body: JSON.stringify(payload),
        });
        emitMetric("login_success", {
            time_to_enter_ms: Math.round(performance.now() - startedAt),
        });
        redirectCustomer(response.customer);
    } catch (error) {
        if (error instanceof ApiError) showError(error.message);
        else {
            console.error("Unexpected demo login error:", error);
            showError("We could not enter the demo. Please try again.");
        }
        if (loginMethod === "customer") selectionInput.value = "";
        emitMetric("login_failure", {
            reason: loginMethod === "customer"
                ? "invalid_or_stale_selection"
                : "unknown_or_inactive_factored_id",
        });
    } finally {
        setSubmitting(false);
    }
}

function handleMethodKeydown(event) {
    if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
    event.preventDefault();
    const nextMethod = loginMethod === "customer" ? "factored-id" : "customer";
    setLoginMethod(nextMethod);
    methodButtons.find((button) => button.dataset.method === nextMethod)?.focus();
}

function handleSearchKeydown(event) {
    if (event.key === "ArrowDown") {
        event.preventDefault();
        if (optionsList.hidden) searchCustomers();
        else setActiveOption(activeIndex + 1);
    } else if (event.key === "ArrowUp") {
        event.preventDefault();
        setActiveOption(activeIndex - 1);
    } else if (event.key === "Enter" && activeIndex >= 0) {
        event.preventDefault();
        chooseOption(options[activeIndex]);
    } else if (event.key === "Escape") {
        closeOptions();
    }
}

async function initializeLogin() {
    try {
        const customer = await getCurrentCustomer();
        if (customer) redirectCustomer(customer);
    } catch (error) {
        console.error("Unable to check current session:", error);
    }
}

searchInput.addEventListener("focus", searchCustomers);
searchInput.addEventListener("input", () => {
    clearError();
    selectionInput.value = "";
    scheduleSearch();
});
searchInput.addEventListener("keydown", handleSearchKeydown);
searchInput.addEventListener("blur", () => window.setTimeout(closeOptions, 100));
factoredIdInput.addEventListener("input", () => {
    clearError();
    factoredIdInput.value = factoredIdInput.value.replace(/\D/g, "").slice(0, 6);
});
methodButtons.forEach((button) => {
    button.addEventListener("click", () => setLoginMethod(button.dataset.method, { focus: true }));
    button.addEventListener("keydown", handleMethodKeydown);
});
form.addEventListener("submit", submitLogin);

initializeLogin();
