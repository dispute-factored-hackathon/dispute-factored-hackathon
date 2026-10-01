import { ApiError, apiRequest } from "../api.js";
import { logout, requireCustomer } from "../auth.js";
import { renderBottomNavigation } from "../components/bottom-nav.js?v=2";
import { initializeGuidedTour } from "../components/guided-tour.js?v=5";

const page = document.querySelector("#profile-page");
const form = document.querySelector("#profile-form");
const factoredId = document.querySelector("#factored-id");
const firstName = document.querySelector("#first-name");
const lastName = document.querySelector("#last-name");
const dateOfBirth = document.querySelector("#date-of-birth");
const gender = document.querySelector("#gender");
const mobilePhone = document.querySelector("#mobile-phone");
const preferredAccent = document.querySelector("#preferred-accent");
const accountStatus = document.querySelector("#account-status");
const errorMessage = document.querySelector("#profile-error");
const successMessage = document.querySelector("#profile-success");
const saveButton = document.querySelector("#save-button");
const logoutButton = document.querySelector("#logout-button");
const bottomNav = document.querySelector("#bottom-nav");

const fieldLabels = {
    date_of_birth: "Birth date",
    first_name: "First name",
    last_name: "Last name",
    mobile_phone: "Mobile phone",
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
    preferredAccent.value = profile.preferred_accent;
    accountStatus.textContent = profile.customer_status;
}

function requestBody() {
    return {
        first_name: firstName.value,
        last_name: lastName.value,
        date_of_birth: dateOfBirth.value,
        gender: gender.value,
        mobile_phone: mobilePhone.value || null,
        preferred_accent: preferredAccent.value,
    };
}

function setSaving(saving) {
    saveButton.disabled = saving;
    saveButton.textContent = saving ? "Saving..." : "Save changes";
}

function profileErrorMessage(error) {
    const validationErrors = error instanceof ApiError
        && Array.isArray(error.details?.detail)
        ? error.details.detail
        : null;

    if (!validationErrors) {
        return error instanceof ApiError
            ? error.message
            : "We could not update your profile. Please try again.";
    }

    return validationErrors.map((validationError) => {
        const field = validationError.loc?.at(-1);
        const label = fieldLabels[field] || "Profile";
        const message = (validationError.msg || "Check this value.")
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
        showMessage(successMessage, "Your profile was updated.");
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
logoutButton.addEventListener("click", () => {
    logout().catch((error) => {
        console.error("Unable to sign out:", error);
        showMessage(errorMessage, "We could not sign you out. Please try again.");
    });
});

initialize();
