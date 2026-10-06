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
} from "../components/guided-tour.js?v=14";


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

const shadyBusiness =
    document.querySelector("#shady-business");

const shadyStartHint =
    document.querySelector("#shady-start-hint");

const shadyLink =
    shadyBusiness?.querySelector(".shady-link");

let shadyStartVisible = false;


function scrollToShadyBusinessStart() {
    const behavior = window.matchMedia("(prefers-reduced-motion: reduce)").matches
        ? "auto"
        : "smooth";
    window.requestAnimationFrame(() => {
        window.requestAnimationFrame(() => {
            shadyBusiness.scrollIntoView({ block: "center", behavior });
            shadyLink?.focus({ preventScroll: true });
        });
    });
}


function showShadyBusinessStart() {
    if (!shadyBusiness || !shadyStartHint || shadyStartVisible) return;
    shadyStartVisible = true;
    shadyBusiness.classList.add("shady-business-start");
    shadyStartHint.hidden = false;
    scrollToShadyBusinessStart();
}


async function openShadyBusiness(event) {
    if (!shadyStartVisible) return;
    event.preventDefault();
    const destination = shadyLink.href;
    shadyBusiness.classList.remove("shady-business-start");
    shadyStartHint.hidden = true;
    try {
        await apiRequest("/onboarding/tour", {
            method: "PATCH",
            body: JSON.stringify({
                status: "completed",
                last_completed_step: "shady-business-started",
            }),
        });
    } catch (error) {
        console.warn("Unable to save the Shady Business starting point:", error);
    }
    window.location.assign(destination);
}


async function restoreShadyBusinessStart() {
    const state = await apiRequest("/onboarding/tour", { method: "GET" });
    const firstExperienceEnded =
        (state.status === "completed" && state.last_completed_step === "finish")
        || (state.status === "skipped"
            && state.last_completed_step === "first-experience-skipped");
    if (firstExperienceEnded) {
        showShadyBusinessStart();
    }
}


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

        await restoreShadyBusinessStart();

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

shadyLink?.addEventListener("click", openShadyBusiness);
window.addEventListener("factored:shady-start", showShadyBusinessStart);


initializeHome();
