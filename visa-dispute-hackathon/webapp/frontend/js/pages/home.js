import {
    logout,
    requireCustomer,
} from "../auth.js";

import {
    renderBottomNavigation,
} from "../components/bottom-nav.js";


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


function greetingForCurrentTime() {
    const hour =
        new Date().getHours();

    if (hour < 12) {
        return "GOOD MORNING";
    }

    if (hour < 18) {
        return "GOOD AFTERNOON";
    }

    return "GOOD EVENING";
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
}


async function initializeHome() {
    try {
        const customer =
            await requireCustomer();

        if (!customer) {
            return;
        }

        if (
            customer.onboarding_completed
            === false
        ) {
            window.location.replace(
                "/onboarding",
            );

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
