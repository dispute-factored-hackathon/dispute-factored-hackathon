import {
    ApiError,
    apiRequest,
} from "../api.js";


const form =
    document.querySelector("#signup-form");

const signupSection =
    document.querySelector("#signup-section");

const successSection =
    document.querySelector("#success-section");

const generateIdButton =
    document.querySelector("#generate-id-button");

const factoredIdInput =
    document.querySelector("#factored-id");

const factoredIdDisplay =
    document.querySelector("#factored-id-display");

const submitButton =
    document.querySelector("#submit-button");

const formError =
    document.querySelector("#form-error");

const successName =
    document.querySelector("#success-name");

const successFactoredId =
    document.querySelector("#success-factored-id");

const cardLastFour =
    document.querySelector("#card-last-four");

const cardStatus =
    document.querySelector("#card-status");

const phoneInput =
    document.querySelector("#mobile-phone");

const phoneAuthMessage =
    document.querySelector("#phone-auth-message");

const continueButton =
    document.querySelector("#continue-button");


const FACTORED_ID_COOKIE =
    "factored_id";

const FACTORED_ID_COOKIE_MAX_AGE =
    60 * 60 * 24 * 30;


function generateFactoredId() {
    const values =
        new Uint32Array(1);

    crypto.getRandomValues(values);

    const number =
        100000
        + (values[0] % 900000);

    return String(number);
}


function displayFactoredId(
    factoredId,
) {
    factoredIdInput.value =
        factoredId;

    factoredIdDisplay.textContent =
        factoredId;

    factoredIdDisplay.classList.remove(
        "factored-id-placeholder",
    );
}


function rememberFactoredId(
    factoredId,
) {
    document.cookie =
        `${FACTORED_ID_COOKIE}=`
        + `${encodeURIComponent(factoredId)}; `
        + `Max-Age=${FACTORED_ID_COOKIE_MAX_AGE}; `
        + "Path=/; "
        + "SameSite=Lax";
}


function normalizePhone(value) {
    const trimmed =
        value.trim();

    if (!trimmed) {
        return "";
    }

    const digits =
        trimmed.replace(
            /\D/g,
            "",
        );

    if (!digits) {
        return "";
    }

    return `+${digits.slice(0, 15)}`;
}


function formatPhoneInput() {
    const normalized =
        normalizePhone(
            phoneInput.value,
        );

    phoneInput.value =
        normalized;
}


function showError(message) {
    formError.textContent =
        message;

    formError.hidden = false;

    formError.scrollIntoView({
        behavior: "smooth",
        block: "center",
    });
}


function clearError() {
    formError.textContent = "";
    formError.hidden = true;
}


function setSubmitting(
    isSubmitting,
) {
    submitButton.disabled =
        isSubmitting;

    generateIdButton.disabled =
        isSubmitting;

    submitButton.textContent =
        isSubmitting
            ? "Creating account..."
            : "Create account";
}


function validateBirthDate() {
    const birthDateInput =
        document.querySelector(
            "#date-of-birth",
        );

    if (!birthDateInput.value) {
        return true;
    }

    const selectedDate =
        new Date(
            `${birthDateInput.value}T00:00:00`,
        );

    const today =
        new Date();

    if (selectedDate >= today) {
        showError(
            "Birth date must be in the past.",
        );

        birthDateInput.focus();

        return false;
    }

    return true;
}


function validatePhone() {
    const phone =
        normalizePhone(
            phoneInput.value,
        );

    if (!phone) {
        phoneInput.value = "";
        return true;
    }

    phoneInput.value = phone;

    const pattern =
        /^\+[1-9]\d{7,14}$/;

    if (!pattern.test(phone)) {
        showError(
            "Enter the country code and phone number. "
            + "For example: +5511981020050.",
        );

        phoneInput.focus();

        return false;
    }

    return true;
}


function validateForm() {
    clearError();

    if (!form.reportValidity()) {
        return false;
    }

    if (!validateBirthDate()) {
        return false;
    }

    if (!validatePhone()) {
        return false;
    }

    if (!factoredIdInput.value) {
        showError(
            "Generate your Factored ID before "
            + "creating the account.",
        );

        generateIdButton.focus();

        return false;
    }

    return true;
}


function buildSignupRequest() {
    const firstName =
        document
            .querySelector(
                "#first-name",
            )
            .value
            .trim();

    const lastName =
        document
            .querySelector(
                "#last-name",
            )
            .value
            .trim();

    const dateOfBirth =
        document
            .querySelector(
                "#date-of-birth",
            )
            .value;

    const gender =
        document
            .querySelector(
                "#gender",
            )
            .value;

    const mobilePhone =
        normalizePhone(
            phoneInput.value,
        );

    const preferredAccent =
        document
            .querySelector(
                "#preferred-accent",
            )
            .value;

    return {
        first_name: firstName,
        last_name: lastName,
        date_of_birth: dateOfBirth,
        gender,
        mobile_phone:
            mobilePhone || null,
        preferred_accent:
            preferredAccent,
        factored_id:
            factoredIdInput.value,
    };
}


function showSuccess(customer) {
    signupSection.hidden = true;
    successSection.hidden = false;

    successName.textContent =
        customer.first_name;

    successFactoredId.textContent =
        customer.factored_id;

    cardLastFour.textContent =
        customer.demo_card.last_four;

    cardStatus.textContent =
        customer
            .demo_card
            .product_status;

    if (customer.mobile_phone) {
        phoneAuthMessage.textContent =
            "When calling Izzy, you can authenticate "
            + "using either your registered phone number "
            + "or your six-digit Factored ID.";
    } else {
        phoneAuthMessage.textContent =
            "When calling Izzy, use your six-digit "
            + "Factored ID to authenticate.";
    }

    successSection.scrollIntoView({
        behavior: "smooth",
        block: "start",
    });
}


async function submitSignup(event) {
    event.preventDefault();

    if (!validateForm()) {
        return;
    }

    setSubmitting(true);
    clearError();

    try {
        const request =
            buildSignupRequest();

        const customer =
            await apiRequest(
                "/customers",
                {
                    method: "POST",
                    body:
                        JSON.stringify(
                            request,
                        ),
                },
            );

        /*
         * Remember the successful demo identity.
         *
         * Do not store the generated ID before the
         * backend has actually created the customer.
         */
        rememberFactoredId(
            customer.factored_id,
        );

        showSuccess(customer);

    } catch (error) {
        if (error instanceof ApiError) {
            console.error(
                "Signup API error",
                {
                    status:
                        error.status,
                    details:
                        error.details,
                },
            );

            showError(
                error.message,
            );

        } else {
            console.error(
                "Unexpected signup error:",
                error,
            );

            showError(
                "We could not create your account. "
                + "Please try again.",
            );
        }

    } finally {
        setSubmitting(false);
    }
}


generateIdButton.addEventListener(
    "click",
    () => {
        clearError();

        displayFactoredId(
            generateFactoredId(),
        );
    },
);


phoneInput.addEventListener(
    "focus",
    () => {
        if (!phoneInput.value) {
            phoneInput.value = "+";
        }
    },
);


phoneInput.addEventListener(
    "input",
    () => {
        const cursorWasAtEnd =
            phoneInput.selectionStart
            === phoneInput.value.length;

        formatPhoneInput();

        if (cursorWasAtEnd) {
            const end =
                phoneInput.value.length;

            phoneInput.setSelectionRange(
                end,
                end,
            );
        }
    },
);


phoneInput.addEventListener(
    "blur",
    () => {
        if (
            phoneInput.value
            === "+"
        ) {
            phoneInput.value = "";
            return;
        }

        formatPhoneInput();
    },
);


form.addEventListener(
    "submit",
    submitSignup,
);


continueButton.addEventListener(
    "click",
    () => {
        window.location.assign(
            "/login",
        );
    },
);
