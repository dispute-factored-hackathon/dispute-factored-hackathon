import { ApiError, apiRequest } from "../api.js";
import { getCurrentCustomer } from "../auth.js";

const form = document.querySelector("#login-form");
const searchInput = document.querySelector("#customer-search");
const selectionInput = document.querySelector("#customer-selection");
const optionsList = document.querySelector("#customer-options");
const loginButton = document.querySelector("#login-button");
const loginError = document.querySelector("#login-error");

let options = [];
let activeIndex = -1;
let searchTimer = null;
let searchController = null;
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
    loginButton.textContent = isSubmitting ? "Entering demo..." : "Enter demo";
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
    if (!selectionInput.value) {
        showError("Search for a customer and choose one of the demo profiles.");
        searchInput.focus();
        emitMetric("login_failure", { reason: "no_selection" });
        return;
    }

    setSubmitting(true);
    try {
        const response = await apiRequest("/auth/demo-login", {
            method: "POST",
            body: JSON.stringify({ selection: selectionInput.value }),
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
        selectionInput.value = "";
        emitMetric("login_failure", { reason: "invalid_or_stale_selection" });
    } finally {
        setSubmitting(false);
    }
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
form.addEventListener("submit", submitLogin);

initializeLogin();
