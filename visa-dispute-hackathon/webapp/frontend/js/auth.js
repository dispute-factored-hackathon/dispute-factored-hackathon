import {
    ApiError,
    apiRequest,
} from "./api.js";


export async function getCurrentCustomer() {
    try {
        return await apiRequest(
            "/auth/me",
            {
                method: "GET",
            },
        );

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
