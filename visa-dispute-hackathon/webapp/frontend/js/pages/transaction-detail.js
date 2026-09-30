import {
    ApiError,
    apiRequest,
} from "../api.js";

import {
    requireCustomer,
} from "../auth.js";

import {
    renderBottomNavigation,
} from "../components/bottom-nav.js";


const page =
    document.querySelector("#transaction-page");

const detail =
    document.querySelector("#transaction-detail");

const pageError =
    document.querySelector("#page-error");

const profileInitial =
    document.querySelector("#profile-initial");

const merchantName =
    document.querySelector("#merchant-name");

const transactionAmount =
    document.querySelector("#transaction-amount");

const transactionDate =
    document.querySelector("#transaction-date");

const transactionStatus =
    document.querySelector("#transaction-status");

const transactionCard =
    document.querySelector("#transaction-card");

const transactionType =
    document.querySelector("#transaction-type");

const transactionCategory =
    document.querySelector("#transaction-category");

const transactionChannel =
    document.querySelector("#transaction-channel");

const merchantCategory =
    document.querySelector("#merchant-category");

const transactionLocation =
    document.querySelector("#transaction-location");

const fraudWarning =
    document.querySelector("#fraud-warning");

const reportButton =
    document.querySelector("#report-button");

const bottomNav =
    document.querySelector("#bottom-nav");


function showError(message) {
    pageError.textContent = message;
    pageError.hidden = false;
}


function formatMoney(
    amount,
    currency,
) {
    try {
        return new Intl.NumberFormat(
            undefined,
            {
                style: "currency",
                currency,
            },
        ).format(amount);

    } catch {
        return `${currency} ${amount.toFixed(2)}`;
    }
}


function formatDate(value) {
    const date =
        new Date(value);

    return new Intl.DateTimeFormat(
        undefined,
        {
            dateStyle: "medium",
            timeStyle: "short",
        },
    ).format(date);
}


function transactionIdFromPath() {
    const parts =
        window.location.pathname
            .split("/")
            .filter(Boolean);

    if (
        parts.length !== 2
        || parts[0] !== "transactions"
    ) {
        return null;
    }

    return decodeURIComponent(
        parts[1],
    );
}


function locationText(transaction) {
    const parts = [
        transaction.transaction_city,
        transaction.transaction_country,
    ].filter(
        (value) =>
            value
            && value !== "Unknown",
    );

    if (parts.length === 0) {
        return "Unknown";
    }

    return parts.join(", ");
}


function renderTransaction(
    transaction,
) {
    merchantName.textContent =
        transaction.merchant_name
        || "Unknown merchant";

    transactionAmount.textContent =
        formatMoney(
            transaction.amount,
            transaction.currency,
        );

    transactionDate.textContent =
        formatDate(
            transaction.transaction_date,
        );

    transactionStatus.textContent =
        transaction.transaction_status;

    transactionCard.textContent =
        `•••• ${transaction.card_last_four}`;

    transactionType.textContent =
        transaction.transaction_type;

    transactionCategory.textContent =
        transaction.transaction_category
        || "—";

    transactionChannel.textContent =
        transaction.channel;

    merchantCategory.textContent =
        transaction.merchant_category
        || "—";

    transactionLocation.textContent =
        locationText(transaction);

    fraudWarning.hidden =
        !transaction.is_fraud;

    reportButton.href =
        "/agent?transaction_id="
        + encodeURIComponent(
            transaction.transaction_id,
        );

    detail.hidden = false;
}


async function loadTransaction(
    transactionId,
) {
    try {
        const transaction =
            await apiRequest(
                `/transactions/${encodeURIComponent(
                    transactionId,
                )}`,
                {
                    method: "GET",
                },
            );

        renderTransaction(
            transaction,
        );

    } catch (error) {
        if (
            error instanceof ApiError
            && error.status === 401
        ) {
            window.location.replace(
                "/login",
            );

            return;
        }

        if (
            error instanceof ApiError
            && error.status === 404
        ) {
            showError(
                "We couldn't find this transaction.",
            );

            return;
        }

        console.error(
            "Unable to load transaction:",
            error,
        );

        showError(
            "We could not load this transaction. "
            + "Please try again.",
        );
    }
}


async function initialize() {
    try {
        const customer =
            await requireCustomer();

        if (!customer) {
            return;
        }

        profileInitial.textContent =
            customer.first_name
                .charAt(0)
                .toUpperCase();

        renderBottomNavigation(
            bottomNav,
            "transactions",
        );

        page.hidden = false;

        const transactionId =
            transactionIdFromPath();

        if (!transactionId) {
            showError(
                "Invalid transaction.",
            );

            return;
        }

        await loadTransaction(
            transactionId,
        );

    } catch (error) {
        console.error(
            "Unable to initialize transaction:",
            error,
        );

        window.location.replace(
            "/login",
        );
    }
}


initialize();
