import {
    requireCustomer,
} from "../auth.js";
import { i18nReady, t } from "../i18n.js?v=1";

await i18nReady;

import {
    renderBottomNavigation,
} from "../components/bottom-nav.js?v=4";

import {
    initializeGuidedTour,
} from "../components/guided-tour.js?v=9";


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
        titleKey: "nav.complaints",
        descriptionKey: "coming.complaints",
        navigationKey: null,
    },

    "/profile": {
        titleKey: "profile.title",
        descriptionKey: "coming.profile",
        navigationKey: null,
    },

    "/agent": {
        titleKey: "coming.izzy_title",
        descriptionKey: "coming.izzy",
        navigationKey: "agent",
    },

    "/shop": {
        titleKey: "coming.store_title",
        descriptionKey: "coming.store",
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
        featureDescription.textContent = t("coming.transaction_context", {
            transactionId,
        });

        return;
    }

    if (intent === "new_complaint") {
        featureDescription.textContent = t("coming.complaint_context");
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
            featureTitle.textContent = t(feature.titleKey);

            featureDescription.textContent = t(feature.descriptionKey);

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
