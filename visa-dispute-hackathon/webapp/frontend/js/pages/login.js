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


const FACTORED_ID_COOKIE =
    "factored_id";


function getCookie(name) {
    const cookies =
        document.cookie
            .split(";")
            .map(
                (cookie) =>
                    cookie.trim(),
            );

    const prefix =
        `${name}=`;

    const cookie =
        cookies.find(
            (candidate) =>
                candidate.startsWith(
                    prefix,
                ),
        );

    if (!cookie) {
        return null;
    }

    return decodeURIComponent(
        cookie.slice(
            prefix.length,
        ),
    );
}


function rememberedFactoredId() {
    const value =
        getCookie(
            FACTORED_ID_COOKIE,
        );

    if (
        !value
        || !/^\d{6}$/.test(value)
    ) {
        return null;
    }

    return value;
}


function prefillFactoredId() {
    const factoredId =
        rememberedFactoredId();

    if (!factoredId) {
        return;
    }

    factoredIdInput.value =
        factoredId;
}


function showError(message) {
    loginError.textContent =
        message;

    loginError.hidden = false;
}


function clearError() {
    loginError.textContent = "";
    loginError.hidden = true;
}


function setSubmitting(
    isSubmitting,
) {
    loginButton.disabled =
        isSubmitting;

    loginButton.textContent =
        isSubmitting
            ? "Signing in..."
            : "Sign in";
}


function normalizeFactoredId() {
    const digits =
        factoredIdInput
            .value
            .replace(/\D/g, "")
            .slice(0, 6);

    factoredIdInput.value =
        digits;

    return digits;
}


function redirectCustomer(
    customer,
) {
    if (
        customer.onboarding_completed
        === false
    ) {
        window.location.replace(
            "/onboarding",
        );

        return;
    }

    window.location.replace(
        "/home",
    );
}


async function redirectIfAuthenticated() {
    try {
        const customer =
            await getCurrentCustomer();

        if (!customer) {
            return false;
        }

        redirectCustomer(
            customer,
        );

        return true;

    } catch (error) {
        console.error(
            "Unable to check current session:",
            error,
        );

        return false;
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
        const response =
            await apiRequest(
                "/auth/login",
                {
                    method: "POST",
                    body:
                        JSON.stringify({
                            factored_id:
                                factoredId,
                        }),
                },
            );

        redirectCustomer(
            response.customer,
        );

    } catch (error) {
        if (error instanceof ApiError) {
            showError(
                error.message,
            );
        } else {
            console.error(
                "Unexpected login error:",
                error,
            );

            showError(
                "We could not sign you in. "
                + "Please try again.",
            );
        }

    } finally {
        setSubmitting(false);
    }
}


async function initializeLogin() {
    prefillFactoredId();

    await redirectIfAuthenticated();
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


initializeLogin();
