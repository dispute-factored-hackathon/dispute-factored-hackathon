import {
    apiRequest,
} from "../api.js";

import {
    requireCustomer,
} from "../auth.js";


const IZZY_PHONE =
    "+16615779964";


const page =
    document.querySelector(
        "#onboarding-page",
    );

const skipButton =
    document.querySelector(
        "#skip-button",
    );

const stepCounter =
    document.querySelector(
        "#step-counter",
    );

const progressBar =
    document.querySelector(
        "#progress-bar",
    );

const stepEyebrow =
    document.querySelector(
        "#step-eyebrow",
    );

const stepTitle =
    document.querySelector(
        "#step-title",
    );

const stepBody =
    document.querySelector(
        "#step-body",
    );

const stepHighlight =
    document.querySelector(
        "#step-highlight",
    );

const stepLink =
    document.querySelector(
        "#step-link",
    );

const previousButton =
    document.querySelector(
        "#previous-button",
    );

const nextButton =
    document.querySelector(
        "#next-button",
    );

const skipDialog =
    document.querySelector(
        "#skip-dialog",
    );

const keepLearningButton =
    document.querySelector(
        "#keep-learning-button",
    );

const confirmSkipButton =
    document.querySelector(
        "#confirm-skip-button",
    );


let customer = null;
let currentStep = 0;


function tutorialSteps() {
    return [
        {
            eyebrow: "WELCOME",
            title:
                "Welcome to the Factored Bank demo.",
            body:
                "This is a synthetic banking environment "
                + "built for the Factored Hackathon. "
                + "No real money moves through this app.",
        },

        {
            eyebrow: "YOUR ACCOUNT",
            title:
                "You have your own demo bank account.",
            body:
                "Your profile includes a Factored Bank "
                + "credit card that you can use throughout "
                + "the demo experience.",
            link: {
                label: "View your cards",
                href: "/cards",
            },
        },

        {
            eyebrow: "SHADY BUSINESS",
            title:
                "Meet our intentionally suspicious store.",
            body:
                "Shady Business is the demo store. "
                + "Use your Factored Bank card there to "
                + "create purchases that appear in your "
                + "bank account.",
            link: {
                label: "Visit Shady Business",
                href: "/shop",
            },
        },

        {
            eyebrow: "MAKE A PURCHASE",
            title:
                "Store purchases become bank transactions.",
            body:
                "When you buy something at Shady Business, "
                + "the purchase is added to your Factored "
                + "Bank transaction history.",
        },

        {
            eyebrow: "WATCH YOUR STATEMENT",
            title:
                "Not every transaction may be what you expected.",
            body:
                "The demo can introduce suspicious or unwanted "
                + "activity so you can experience the dispute "
                + "journey from a customer's perspective.",
        },

        {
            eyebrow: "TRANSACTIONS",
            title:
                "Review your activity in Factored Bank.",
            body:
                "Open Transactions to inspect purchases. "
                + "Select a transaction to see its details. "
                + "If something looks wrong, choose "
                + "\"Report this transaction\".",
            link: {
                label: "View transactions",
                href: "/transactions",
            },
        },

        {
            eyebrow: "MEET IZZY",
            title:
                "Izzy helps you resolve payment problems.",
            body:
                "Reporting a transaction starts a conversation "
                + "with Izzy, Factored Bank's dispute assistant. "
                + "Izzy receives the selected transaction as "
                + "context and guides you through the dispute.",
            link: {
                label: "Open Izzy",
                href: "/agent",
            },
        },

        {
            eyebrow: "CALL IZZY",
            title:
                "You can also handle a dispute by telephone.",
            body:
                "Prefer speaking instead of chatting? "
                + "Call Izzy directly from your phone.",
            highlight: {
                type: "phone",
            },
            link: {
                label: "Call Izzy",
                href: `tel:${IZZY_PHONE}`,
            },
        },

        {
            eyebrow: "TELEPHONE AUTHENTICATION",
            title:
                "Keep your Factored ID handy.",
            body:
                "When calling Izzy, you can authenticate "
                + "using your registered phone number or "
                + "your Factored ID. If document authentication "
                + "is used, enter the six digits using your "
                + "telephone keypad.",
            highlight: {
                type: "factored_id",
            },
        },

        {
            eyebrow: "YOUR DISPUTES",
            title:
                "Follow what happens after you report it.",
            body:
                "Your complaints page shows previous disputes, "
                + "claimed amounts, current status and resolution "
                + "information. You're ready to explore the demo.",
            link: {
                label: "View complaints",
                href: "/complaints",
            },
        },
    ];
}


function getFactoredIdCookie() {
    const cookie =
        document.cookie
            .split(";")
            .map(
                (item) =>
                    item.trim(),
            )
            .find(
                (item) =>
                    item.startsWith(
                        "factored_id=",
                    ),
            );

    if (!cookie) {
        return null;
    }

    return decodeURIComponent(
        cookie.slice(
            "factored_id=".length,
        ),
    );
}


function clearStepExtras() {
    stepHighlight.hidden = true;
    stepHighlight.replaceChildren();

    stepLink.hidden = true;
    stepLink.textContent = "";

    stepLink.removeAttribute(
        "href",
    );
}


function renderFactoredId() {
    const factoredId =
        customer?.factored_id
        || getFactoredIdCookie();

    const label =
        document.createElement("span");

    label.textContent =
        "YOUR FACTORED ID";

    const value =
        document.createElement("strong");

    value.textContent =
        factoredId
        || "Not available";

    stepHighlight.append(
        label,
        value,
    );
}


function renderPhone() {
    const label =
        document.createElement("span");

    label.textContent =
        "CALL IZZY";

    const phone =
        document.createElement("a");

    phone.className =
        "highlight-phone";

    phone.href =
        `tel:${IZZY_PHONE}`;

    phone.textContent =
        "+1 661 577 9964";

    stepHighlight.append(
        label,
        phone,
    );
}


function renderHighlight(
    highlight,
) {
    if (!highlight) {
        return;
    }

    stepHighlight.hidden = false;

    if (
        highlight.type
        === "factored_id"
    ) {
        renderFactoredId();
        return;
    }

    if (
        highlight.type
        === "phone"
    ) {
        renderPhone();
    }
}


function renderStep() {
    const steps =
        tutorialSteps();

    const step =
        steps[currentStep];

    clearStepExtras();

    stepCounter.textContent =
        `${currentStep + 1} of ${steps.length}`;

    progressBar.style.width =
        `${
            (
                (currentStep + 1)
                / steps.length
            )
            * 100
        }%`;

    stepEyebrow.textContent =
        step.eyebrow;

    stepTitle.textContent =
        step.title;

    stepBody.textContent =
        step.body;

    renderHighlight(
        step.highlight,
    );

    if (step.link) {
        stepLink.textContent =
            step.link.label;

        stepLink.href =
            step.link.href;

        stepLink.hidden = false;
    }

    previousButton.disabled =
        currentStep === 0;

    nextButton.textContent =
        currentStep
        === steps.length - 1
            ? "Finish"
            : "Next";
}


async function completeTutorial() {
    nextButton.disabled = true;
    skipButton.disabled = true;

    try {
        await apiRequest(
            "/onboarding/complete",
            {
                method: "POST",
            },
        );

        window.location.replace(
            "/home",
        );

    } catch (error) {
        console.error(
            "Unable to complete onboarding:",
            error,
        );

        nextButton.disabled = false;
        skipButton.disabled = false;
    }
}


async function handleNext() {
    const steps =
        tutorialSteps();

    if (
        currentStep
        === steps.length - 1
    ) {
        await completeTutorial();
        return;
    }

    currentStep += 1;

    renderStep();

    window.scrollTo({
        top: 0,
        behavior: "smooth",
    });
}


function handlePrevious() {
    if (currentStep === 0) {
        return;
    }

    currentStep -= 1;

    renderStep();

    window.scrollTo({
        top: 0,
        behavior: "smooth",
    });
}


function openSkipDialog() {
    if (
        typeof skipDialog.showModal
        === "function"
    ) {
        skipDialog.showModal();
        return;
    }

    completeTutorial().catch(
        (error) => {
            console.error(
                "Unable to skip onboarding:",
                error,
            );
        },
    );
}


function closeSkipDialog() {
    if (skipDialog.open) {
        skipDialog.close();
    }
}


async function initialize() {
    try {
        customer =
            await requireCustomer();

        if (!customer) {
            return;
        }

        currentStep = 0;

        renderStep();

        page.hidden = false;

    } catch (error) {
        console.error(
            "Unable to initialize onboarding:",
            error,
        );

        window.location.replace(
            "/login",
        );
    }
}


nextButton.addEventListener(
    "click",
    () => {
        handleNext().catch(
            (error) => {
                console.error(
                    "Unable to advance onboarding:",
                    error,
                );
            },
        );
    },
);


previousButton.addEventListener(
    "click",
    handlePrevious,
);


skipButton.addEventListener(
    "click",
    openSkipDialog,
);


keepLearningButton.addEventListener(
    "click",
    closeSkipDialog,
);


confirmSkipButton.addEventListener(
    "click",
    () => {
        closeSkipDialog();

        completeTutorial().catch(
            (error) => {
                console.error(
                    "Unable to skip onboarding:",
                    error,
                );
            },
        );
    },
);


skipDialog.addEventListener(
    "cancel",
    (event) => {
        event.preventDefault();
        closeSkipDialog();
    },
);


initialize();
