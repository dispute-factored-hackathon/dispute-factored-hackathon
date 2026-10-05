import { ApiError, apiRequest } from "../api.js";
import { logout, requireCustomer } from "../auth.js";
import {
    i18nReady,
    setLocale,
    t,
    translateValue,
} from "../i18n.js?v=1";
import { renderBottomNavigation } from "../components/bottom-nav.js?v=4";
import { initializeGuidedTour } from "../components/guided-tour.js?v=11";

await i18nReady;

const page = document.querySelector("#profile-page");
const form = document.querySelector("#profile-form");
const factoredId = document.querySelector("#factored-id");
const firstName = document.querySelector("#first-name");
const lastName = document.querySelector("#last-name");
const dateOfBirth = document.querySelector("#date-of-birth");
const gender = document.querySelector("#gender");
const mobilePhone = document.querySelector("#mobile-phone");
const preferredLocale = document.querySelector("#preferred-locale");
const accountStatus = document.querySelector("#account-status");
const errorMessage = document.querySelector("#profile-error");
const successMessage = document.querySelector("#profile-success");
const saveButton = document.querySelector("#save-button");
const logoutButton = document.querySelector("#logout-button");
const bottomNav = document.querySelector("#bottom-nav");

const fieldLabels = {
    date_of_birth: "signup.birth_date",
    first_name: "signup.first_name",
    last_name: "signup.last_name",
    mobile_phone: "signup.mobile",
};

function showMessage(element, message) {
    element.textContent = message;
    element.hidden = false;
}

function clearMessages() {
    errorMessage.hidden = true;
    successMessage.hidden = true;
    errorMessage.textContent = "";
    successMessage.textContent = "";
}

function renderProfile(profile) {
    factoredId.value = profile.factored_id;
    firstName.value = profile.first_name;
    lastName.value = profile.last_name;
    dateOfBirth.value = profile.date_of_birth;
    gender.value = profile.gender;
    mobilePhone.value = profile.mobile_phone || "";
    const localeByAccent = {
        english: "en-US",
        portuguese: "pt-BR",
        argentine_spanish: "es-AR",
        colombian_spanish: "es-CO",
        mexican_spanish: "es-MX",
    };
    const supportedLocales = new Set(["en-US", "pt-BR", "es-AR", "es-CO", "es-MX"]);
    preferredLocale.value = supportedLocales.has(profile.preferred_locale)
        ? profile.preferred_locale
        : localeByAccent[profile.preferred_accent] || "en-US";
    accountStatus.textContent = translateValue(profile.customer_status);
}

function requestBody() {
    return {
        first_name: firstName.value,
        last_name: lastName.value,
        date_of_birth: dateOfBirth.value,
        gender: gender.value,
        mobile_phone: mobilePhone.value || null,
        preferred_accent: {
            "en-US": "english",
            "pt-BR": "portuguese",
            "es-AR": "argentine_spanish",
            "es-CO": "colombian_spanish",
            "es-MX": "mexican_spanish",
        }[preferredLocale.value],
        preferred_locale: preferredLocale.value,
    };
}

function setSaving(saving) {
    saveButton.disabled = saving;
    saveButton.textContent = t(saving ? "profile.saving" : "profile.save");
}

function profileErrorMessage(error) {
    const validationErrors = error instanceof ApiError
        && Array.isArray(error.details?.detail)
        ? error.details.detail
        : null;

    if (!validationErrors) {
        return error instanceof ApiError
            ? translateValue(error.message)
            : t("profile.generic_error");
    }

    return validationErrors.map((validationError) => {
        const field = validationError.loc?.at(-1);
        const label = fieldLabels[field] ? t(fieldLabels[field]) : t("nav.profile");
        const message = translateValue(validationError.msg || t("profile.value_error"))
            .replace(/^Value error,\s*/i, "");
        return `${label}: ${message}`;
    }).join(" · ");
}

async function saveProfile(event) {
    event.preventDefault();
    clearMessages();

    if (!form.reportValidity()) {
        return;
    }

    setSaving(true);
    try {
        const profile = await apiRequest("/customers/profile", {
            method: "PATCH",
            body: JSON.stringify(requestBody()),
        });
        renderProfile(profile);
        await setLocale(profile.preferred_locale, { persistCustomer: true });
        showMessage(successMessage, t("profile.updated"));
    } catch (error) {
        showMessage(errorMessage, profileErrorMessage(error));
    } finally {
        setSaving(false);
    }
}

async function initialize() {
    try {
        dateOfBirth.max = new Date().toISOString().slice(0, 10);
        const customer = await requireCustomer();
        if (!customer) {
            return;
        }

        const profile = await apiRequest("/customers/profile", { method: "GET" });
        renderProfile(profile);
        renderBottomNavigation(bottomNav, null);
        page.hidden = false;
        await initializeGuidedTour(customer);
    } catch (error) {
        console.error("Unable to initialize profile:", error);
        window.location.replace("/login");
    }
}

form.addEventListener("submit", saveProfile);
preferredLocale.addEventListener("change", async () => {
    await setLocale(preferredLocale.value);
});
logoutButton.addEventListener("click", () => {
    logout().catch((error) => {
        console.error("Unable to sign out:", error);
        showMessage(errorMessage, t("profile.logout_error"));
    });
});

initialize();
