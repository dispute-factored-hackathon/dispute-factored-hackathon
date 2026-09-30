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
    document.querySelector("#transactions-page");

const list =
    document.querySelector("#transactions-list");

const emptyState =
    document.querySelector("#empty-state");

const fraudNotice =
    document.querySelector("#fraud-notice");

const pageError =
    document.querySelector("#page-error");

const profileInitial =
    document.querySelector("#profile-initial");

const bottomNav =
    document.querySelector("#bottom-nav");


function showError(message) {
    pageError.textContent = message;
    pageError.hidden = false;
}


function clearError() {
    pageError.textContent = "";
    pageError.hidden = true;
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
            month: "short",
            day: "numeric",
            year: "numeric",
        },
    ).format(date);
}


function createTransactionItem(
    transaction,
) {
    const item =
        document.createElement("a");

    item.className =
        "transaction-item";

    item.href =
        `/transactions/${encodeURIComponent(
            transaction.transaction_id,
        )}`;

    const icon =
        document.createElement("span");

    icon.className =
        transaction.is_fraud
            ? "transaction-icon is-suspicious"
            : "transaction-icon";

    icon.setAttribute(
        "aria-hidden",
        "true",
    );

    icon.textContent =
        transaction.is_fraud
            ? "!"
            : "↗";

    const main =
        document.createElement("div");

    main.className =
        "transaction-main";

    const merchant =
        document.createElement("p");

    merchant.className =
        "transaction-merchant";

    merchant.textContent =
        transaction.merchant_name
        || "Unknown merchant";

    const meta =
        document.createElement("div");

    meta.className =
        "transaction-meta";

    const date =
        document.createElement("span");

    date.textContent =
        formatDate(
            transaction.transaction_date,
        );

    const card =
        document.createElement("span");

    card.textContent =
        `Card •••• ${transaction.card_last_four}`;

    meta.append(
        date,
        document.createTextNode("·"),
        card,
    );

    main.append(
        merchant,
        meta,
    );

    const side =
        document.createElement("div");

    side.className =
        "transaction-side";

    const amount =
        document.createElement("span");

    amount.className =
        "transaction-amount";

    amount.textContent =
        formatMoney(
            transaction.amount,
            transaction.currency,
        );

    const status =
        document.createElement("span");

    status.className =
        "transaction-status";

    status.textContent =
        transaction.transaction_status;

    side.append(
        amount,
        status,
    );

    if (transaction.is_fraud) {
        const fraudBadge =
            document.createElement("span");

        fraudBadge.className =
            "fraud-badge";

        fraudBadge.textContent =
            "Suspicious";

        side.append(fraudBadge);
    }

    item.append(
        icon,
        main,
        side,
    );

    return item;
}


function renderTransactions(
    transactions,
) {
    list.replaceChildren();

    if (transactions.length === 0) {
        emptyState.hidden = false;
        fraudNotice.hidden = true;
        return;
    }

    emptyState.hidden = true;

    fraudNotice.hidden =
        !transactions.some(
            (transaction) =>
                transaction.is_fraud,
        );

    for (
        const transaction
        of transactions
    ) {
        list.append(
            createTransactionItem(
                transaction,
            ),
        );
    }
}


async function loadTransactions() {
    clearError();

    try {
        const transactions =
            await apiRequest(
                "/transactions",
                {
                    method: "GET",
                },
            );

        renderTransactions(
            transactions,
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

        console.error(
            "Unable to load transactions:",
            error,
        );

        showError(
            "We could not load your transactions. "
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

        await loadTransactions();

    } catch (error) {
        console.error(
            "Unable to initialize transactions:",
            error,
        );

        window.location.replace(
            "/login",
        );
    }
}


initialize();
