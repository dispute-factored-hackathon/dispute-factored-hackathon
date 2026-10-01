import {
    ApiError,
    apiRequest,
} from "./api.js";


export async function getCurrentCustomer() {
    try {
        const customer = await apiRequest(
            "/auth/me",
            {
                method: "GET",
            },
        );

        localStorage.setItem("factored_locale", customer.locale);
        document.documentElement.lang = customer.locale;

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

    window.location.replace("/login");
}
