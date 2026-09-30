import {
    ApiError,
    apiRequest,
} from "../api.js";

import {
    getCurrentCustomer,
} from "../auth.js";


const form =
    document.querySelector("#login-form");

const factoredIdInput =
    document.querySelector("#factored-id");

const loginButton =
    document.querySelector("#login-button");

const loginError =
    document.querySelector("#login-error");


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

    loginButton.textContent =
        isSubmitting
            ? "Signing in..."
            : "Sign in";
}


function normalizeFactoredId() {
    const digits =
        factoredIdInput.value
            .replace(/\D/g, "")
            .slice(0, 6);

    factoredIdInput.value = digits;

    return digits;
}


async function redirectIfAuthenticated() {
    try {
        const customer =
            await getCurrentCustomer();

        if (customer) {
            window.location.replace("/home");
        }
    } catch (error) {
        console.error(
            "Unable to check current session:",
            error,
        );
    }
}


async function submitLogin(event) {
    event.preventDefault();

    clearError();

    const factoredId =
        normalizeFactoredId();

    if (factoredId.length !== 6) {
        showError(
            "Enter your six-digit Factored ID.",
        );

        factoredIdInput.focus();

        return;
    }

    setSubmitting(true);

    try {
        await apiRequest(
            "/auth/login",
            {
                method: "POST",
                body: JSON.stringify({
                    factored_id: factoredId,
                }),
            },
        );

        window.location.replace("/home");

    } catch (error) {
        if (error instanceof ApiError) {
            showError(error.message);
        } else {
            console.error(
                "Unexpected login error:",
                error,
            );

            showError(
                "We could not sign you in. " +
                "Please try again.",
            );
        }

    } finally {
        setSubmitting(false);
    }
}


factoredIdInput.addEventListener(
    "input",
    () => {
        clearError();
        normalizeFactoredId();
    },
);


form.addEventListener(
    "submit",
    submitLogin,
);


redirectIfAuthenticated();
