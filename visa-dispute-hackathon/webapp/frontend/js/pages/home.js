import { apiRequest } from "../api.js";
import {
    logout,
    requireCustomer,
} from "../auth.js";
import { i18nReady, t } from "../i18n.js?v=1";

await i18nReady;

import {
    renderBottomNavigation,
} from "../components/bottom-nav.js?v=4";

import {
    initializeGuidedTour,
} from "../components/guided-tour.js?v=8";


const homePage =
    document.querySelector("#home-page");

const customerName =
    document.querySelector("#customer-name");

const profileInitial =
    document.querySelector("#profile-initial");

const greeting =
    document.querySelector("#greeting");

const logoutButton =
    document.querySelector("#logout-button");

const bottomNav =
    document.querySelector("#bottom-nav");

const tutorialReplay =
    document.querySelector("#tutorial-replay");


function greetingForCurrentTime() {
    const hour =
        new Date().getHours();

    if (hour < 12) {
        return t("home.morning");
    }

    if (hour < 18) {
        return t("home.afternoon");
    }

    return t("home.evening");
}


function displayCustomer(customer) {
    customerName.textContent =
        customer.first_name;

    profileInitial.textContent =
        customer.first_name
            .charAt(0)
            .toUpperCase();

    greeting.textContent =
        greetingForCurrentTime();

    tutorialReplay.hidden =
        !customer.onboarding_eligible;
}


async function displayIzzyPhone() {
    try {
        const contact = await apiRequest("/izzy/contact", { method: "GET" });
        for (const link of document.querySelectorAll(".phone-number, .call-button")) {
            link.href = `tel:${contact.phone_number}`;
        }
        const number = document.querySelector(".phone-number");
        if (number) number.textContent = contact.phone_display;
    } catch (error) {
        console.warn("Unable to load Izzy's phone line; keeping the default:", error);
    }
}


async function initializeHome() {
    try {
        const customer =
            await requireCustomer();

        if (!customer) {
            return;
        }

        displayCustomer(
            customer,
        );

        renderBottomNavigation(
            bottomNav,
            "home",
        );

        homePage.hidden = false;

        displayIzzyPhone();

        await initializeGuidedTour(
            customer,
        );

    } catch (error) {
        console.error(
            "Unable to initialize customer home:",
            error,
        );

        window.location.replace(
            "/login",
        );
    }
}


async function handleLogout() {
    logoutButton.disabled = true;

    try {
        await logout();

    } catch (error) {
        console.error(
            "Unable to sign out:",
            error,
        );

        logoutButton.disabled = false;
    }
}


logoutButton.addEventListener(
    "click",
    handleLogout,
);


initializeHome();
