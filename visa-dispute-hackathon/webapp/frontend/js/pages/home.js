import {
    logout,
    requireCustomer,
} from "../auth.js";


const homePage =
    document.querySelector("#home-page");

const customerName =
    document.querySelector("#customer-name");

const logoutButton =
    document.querySelector("#logout-button");


async function initializeHome() {
    try {
        const customer =
            await requireCustomer();

        if (!customer) {
            return;
        }

        customerName.textContent =
            customer.first_name;

        homePage.hidden = false;

    } catch (error) {
        console.error(
            "Unable to initialize customer home:",
            error,
        );

        window.location.replace("/login");
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
