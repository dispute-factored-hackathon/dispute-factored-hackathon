import {
    requireCustomer,
} from "../auth.js";

import {
    renderBottomNavigation,
} from "../components/bottom-nav.js";


const page =
    document.querySelector("#coming-soon-page");

const featureTitle =
    document.querySelector("#feature-title");

const featureDescription =
    document.querySelector("#feature-description");

const bottomNav =
    document.querySelector("#bottom-nav");


const FEATURES = {
    "/cards": {
        title: "Your cards",
        description:
            "View your Factored Bank cards, check their status, " +
            "and block or unblock them when needed.",
        navigationKey: "cards",
    },

    "/transactions": {
        title: "Transactions",
        description:
            "Review your purchases and payment activity, " +
            "and report a transaction you don't recognize.",
        navigationKey: "transactions",
    },

    "/complaints": {
        title: "Complaints",
        description:
            "Follow complaints and disputes you have opened " +
            "with Factored Bank.",
        navigationKey: null,
    },

    "/profile": {
        title: "Your profile",
        description:
            "Review your Factored Bank demo identity and " +
            "personal preferences.",
        navigationKey: null,
    },

    "/agent": {
        title: "Izzy",
        description:
            "Chat with Izzy about a payment, transaction, " +
            "or dispute.",
        navigationKey: "agent",
    },

    "/shop": {
        title: "Shady Business",
        description:
            "The suspicious demo shop is being prepared. " +
            "Soon you'll be able to make purchases here " +
            "and generate transactions to dispute.",
        navigationKey: null,
    },
};


async function initializePage() {
    try {
        const customer =
            await requireCustomer();

        if (!customer) {
            return;
        }

        const feature =
            FEATURES[window.location.pathname];

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

        page.hidden = false;

    } catch (error) {
        console.error(
            "Unable to initialize page:",
            error,
        );

        window.location.replace("/login");
    }
}


initializePage();
