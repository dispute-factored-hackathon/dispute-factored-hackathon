import {
    requireCustomer,
} from "../auth.js";

import {
    renderBottomNavigation,
} from "../components/bottom-nav.js?v=2";

import {
    initializeGuidedTour,
} from "../components/guided-tour.js";


const page =
    document.querySelector("#coming-soon-page");

const featureTitle =
    document.querySelector("#feature-title");

const featureDescription =
    document.querySelector("#feature-description");

const bottomNav =
    document.querySelector("#bottom-nav");


const FEATURES = {
    "/complaints": {
        title: "Complaints",
        description:
            "Follow complaints and disputes you have opened "
            + "with Factored Bank.",
        navigationKey: null,
    },

    "/profile": {
        title: "Your profile",
        description:
            "Review your Factored Bank demo identity and "
            + "personal preferences.",
        navigationKey: null,
    },

    "/agent": {
        title: "Izzy",
        description:
            "Chat with Izzy about a payment, transaction, "
            + "or dispute.",
        navigationKey: "agent",
    },

    "/shop": {
        title: "Shady Business",
        description:
            "The suspicious demo shop is being prepared. "
            + "Soon you'll be able to make purchases here "
            + "and generate transactions to dispute.",
        navigationKey: null,
    },
};

function applyAgentContext() {
    if (
        window.location.pathname
        !== "/agent"
    ) {
        return;
    }

    const parameters =
        new URLSearchParams(
            window.location.search,
        );

    const transactionId =
        parameters.get(
            "transaction_id",
        );

    const intent =
        parameters.get(
            "intent",
        );

    if (transactionId) {
        featureDescription.textContent =
            "Izzy received the transaction you selected "
            + `(${transactionId}). The chat experience will `
            + "use this transaction as its starting context.";

        return;
    }

    if (intent === "new_complaint") {
        featureDescription.textContent =
            "Izzy is ready to help you start a new complaint. "
            + "The chat experience will begin in the "
            + "complaint workflow.";
    }
}


async function initializePage() {
    try {
        const customer =
            await requireCustomer();

        if (!customer) {
            return;
        }

        const feature =
            FEATURES[
                window.location.pathname
            ];

        if (feature) {
            featureTitle.textContent =
                feature.title;

            featureDescription.textContent =
                feature.description;

            renderBottomNavigation(
                bottomNav,
                feature.navigationKey,
            );
        } else {
            renderBottomNavigation(
                bottomNav,
                null,
            );
        }

        applyAgentContext();

        page.hidden = false;

        await initializeGuidedTour();

    } catch (error) {
        console.error(
            "Unable to initialize page:",
            error,
        );

        window.location.replace(
            "/login",
        );
    }
}


initializePage();
