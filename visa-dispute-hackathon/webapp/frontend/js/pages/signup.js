import {
    ApiError,
    apiRequest,
} from "../api.js";
import {
    getLocale,
    i18nReady,
    setLocale,
    t,
    translateValue,
} from "../i18n.js?v=1";

await i18nReady;

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

const preferredLocaleInput =
    document.querySelector("#preferred-locale");

const firstNameInput =
    document.querySelector("#first-name");

const lastNameInput =
    document.querySelector("#last-name");

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


function normalizedName(value) {
    return value
        .normalize("NFKC")
        .replace(/\s+/g, " ")
        .trim();
}


function normalizeAutofilledNames() {
    let firstName = normalizedName(firstNameInput.value);
    let lastName = normalizedName(lastNameInput.value);

    if (firstName && !lastName) {
        const parts = firstName.split(" ");
        if (parts.length > 1) {
            firstName = parts.shift();
            lastName = parts.join(" ");
        }
    }

    const repeatedLastName = lastName
        && firstName.toLocaleLowerCase().endsWith(` ${lastName.toLocaleLowerCase()}`);
    if (repeatedLastName) {
        firstName = firstName.slice(0, -(lastName.length + 1));
    }

    firstNameInput.value = firstName;
    lastNameInput.value = lastName;
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

    submitButton.textContent = t(
        isSubmitting ? "signup.creating" : "signup.create",
    );
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
        showError(t("signup.birth_error"));

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
        showError(t("signup.phone_error"));

        phoneInput.focus();

        return false;
    }

    return true;
}


function validateForm() {
    clearError();
    normalizeAutofilledNames();

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
        showError(t("signup.generate_error"));

        generateIdButton.focus();

        return false;
    }

    return true;
}


function buildSignupRequest() {
    const firstName = firstNameInput.value;

    const lastName = lastNameInput.value;

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

    const preferredLocale =
        preferredLocaleInput.value;

    const preferredAccent = {
        "en-US": "english",
        "pt-BR": "portuguese",
        "es-AR": "argentine_spanish",
        "es-CO": "colombian_spanish",
        "es-MX": "mexican_spanish",
    }[preferredLocale];

    return {
        first_name: firstName,
        last_name: lastName,
        date_of_birth: dateOfBirth,
        gender,
        mobile_phone:
            mobilePhone || null,
        preferred_accent:
            preferredAccent,
        preferred_locale:
            preferredLocale,
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

    cardStatus.textContent = translateValue(customer.demo_card.product_status);

    if (customer.mobile_phone) {
        phoneAuthMessage.textContent = t("signup.phone_or_id");
    } else {
        phoneAuthMessage.textContent = t("signup.phone_id");
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

            showError(translateValue(error.message));

        } else {
            console.error(
                "Unexpected signup error:",
                error,
            );

            showError(t("signup.generic_error"));
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


preferredLocaleInput.value =
    getLocale().startsWith("pt")
        ? "pt-BR"
        : getLocale().startsWith("es")
            ? "es-419"
            : "en-US";


preferredLocaleInput.addEventListener(
    "change",
    async () => {
        await setLocale(preferredLocaleInput.value);
    },
);


continueButton.addEventListener(
    "click",
    () => {
        window.location.assign(
            "/login",
        );
    },
);
