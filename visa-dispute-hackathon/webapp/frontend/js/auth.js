import {
    ApiError,
    apiRequest,
} from "./api.js";
import {
    clearCustomerLocale,
    setLocale,
} from "./i18n.js?v=1";


export async function getCurrentCustomer() {
    try {
        const customer = await apiRequest(
            "/auth/me",
            {
                method: "GET",
            },
        );

        if (customer.locale_source === "customer") {
            await setLocale(customer.locale, { persistCustomer: true });
        }

        return customer;

    } catch (error) {
        if (
            error instanceof ApiError &&
            error.status === 401
        ) {
            return null;
        }

        throw error;
    }
}


export async function requireCustomer() {
    const customer =
        await getCurrentCustomer();

    if (!customer) {
        window.location.replace("/login");
        return null;
    }

    return customer;
}


export async function logout() {
    await apiRequest(
        "/auth/logout",
        {
            method: "POST",
        },
    );

    clearCustomerLocale();

    window.location.replace("/login");
}
