import {
    ApiError,
    apiRequest,
} from "../api.js";
import {
    i18nReady,
    t,
    translateValue,
} from "../i18n.js?v=1";

await i18nReady;

import {
    requireCustomer,
} from "../auth.js";

import {
    renderBottomNavigation,
} from "../components/bottom-nav.js?v=4";

import {
    initializeGuidedTour,
} from "../components/guided-tour.js?v=10";


const cardsPage =
    document.querySelector("#cards-page");

const cardsList =
    document.querySelector("#cards-list");

const emptyState =
    document.querySelector("#empty-state");

const pageError =
    document.querySelector("#page-error");

const profileInitial =
    document.querySelector("#profile-initial");

const bottomNav =
    document.querySelector("#bottom-nav");

const statusDialog =
    document.querySelector("#status-dialog");

const dialogTitle =
    document.querySelector("#dialog-title");

const dialogDescription =
    document.querySelector("#dialog-description");

const dialogCancel =
    document.querySelector("#dialog-cancel");

const dialogConfirm =
    document.querySelector("#dialog-confirm");


let pendingAction = null;


function showError(message) {
    pageError.textContent = message;
    pageError.hidden = false;
}


function clearError() {
    pageError.textContent = "";
    pageError.hidden = true;
}


function isBlocked(product) {
    return (
        product.product_status
            .toLowerCase()
        === "blocked"
    );
}


function createStatus(product) {
    const status =
        document.createElement("span");

    const blocked =
        isBlocked(product);

    status.className =
        blocked
            ? "card-status card-status-blocked"
            : "card-status card-status-active";

    status.textContent = t(blocked ? "common.blocked" : "common.active");

    return status;
}


function createBankCard(product) {
    const container =
        document.createElement("article");

    container.className =
        "bank-card-container";

    container.dataset.productId =
        product.product_id;

    const card =
        document.createElement("div");

    card.className =
        isBlocked(product)
            ? "bank-card is-blocked"
            : "bank-card is-active";

    const top =
        document.createElement("div");

    top.className = "card-top";

    const brand =
        document.createElement("span");

    brand.className = "card-brand";
    brand.textContent = "FACTORED BANK";

    const type =
        document.createElement("span");

    type.className = "card-type";
    type.textContent = product.product_type;

    top.append(
        brand,
        type,
    );

    const number =
        document.createElement("div");

    number.className = "card-number";
    number.textContent =
        product.masked_number;

    const bottom =
        document.createElement("div");

    bottom.className = "card-bottom";

    const currency =
        document.createElement("span");

    currency.className =
        "card-currency";

    currency.textContent =
        product.currency;

    const status =
        createStatus(product);

    bottom.append(
        currency,
        status,
    );

    card.append(
        top,
        number,
        bottom,
    );

    const controls =
        createControls(product);

    container.append(
        card,
        controls,
    );

    return container;
}


function createControls(product) {
    const controls =
        document.createElement("div");

    controls.className =
        "card-controls";

    const copy =
        document.createElement("div");

    copy.className =
        "card-controls-copy";

    const title =
        document.createElement("strong");

    const description =
        document.createElement("span");

    const action =
        document.createElement("button");

    action.type = "button";

    action.className =
        "button card-action";

    if (isBlocked(product)) {
        title.textContent = t("cards.blocked_title");

        description.textContent = t("cards.blocked_help");

        action.textContent = t("cards.unblock");

        action.classList.add(
            "unblock-action",
        );

        action.addEventListener(
            "click",
            () => {
                openStatusDialog(
                    product,
                    "unblock",
                );
            },
        );

    } else {
        title.textContent = t("cards.active_title");

        description.textContent = t("cards.active_help");

        action.textContent = t("cards.block");

        action.classList.add(
            "block-action",
        );

        action.addEventListener(
            "click",
            () => {
                openStatusDialog(
                    product,
                    "block",
                );
            },
        );
    }

    copy.append(
        title,
        description,
    );

    controls.append(
        copy,
        action,
    );

    return controls;
}


function renderCards(products) {
    cardsList.replaceChildren();

    if (products.length === 0) {
        emptyState.hidden = false;
        return;
    }

    emptyState.hidden = true;

    for (const product of products) {
        cardsList.append(
            createBankCard(product),
        );
    }
}


function openStatusDialog(
    product,
    action,
) {
    pendingAction = {
        product,
        action,
    };

    const blocking =
        action === "block";

    dialogTitle.textContent = t(
        blocking ? "cards.block_question" : "cards.unblock_question",
    );

    dialogDescription.textContent = t(
        blocking ? "cards.block_detail" : "cards.unblock_detail",
        { lastFour: product.last_four },
    );

    dialogConfirm.textContent = t(
        blocking ? "cards.block_action" : "cards.unblock_action",
    );

    dialogConfirm.classList.toggle(
        "block-action",
        blocking,
    );

    dialogConfirm.classList.toggle(
        "unblock-action",
        !blocking,
    );

    statusDialog.showModal();
}


function closeStatusDialog() {
    pendingAction = null;

    if (statusDialog.open) {
        statusDialog.close();
    }
}


async function changeCardStatus() {
    if (!pendingAction) {
        return;
    }

    const {
        product,
        action,
    } = pendingAction;

    dialogConfirm.disabled = true;
    dialogCancel.disabled = true;

    clearError();

    try {
        await apiRequest(
            `/products/${product.product_id}/${action}`,
            {
                method: "POST",
            },
        );

        closeStatusDialog();

        await loadCards();

    } catch (error) {
        closeStatusDialog();

        if (error instanceof ApiError) {
            showError(translateValue(error.message));
        } else {
            console.error(
                "Unable to change card status:",
                error,
            );

            showError(t("cards.update_error"));
        }

    } finally {
        dialogConfirm.disabled = false;
        dialogCancel.disabled = false;
    }
}


async function loadCards() {
    clearError();

    try {
        const products =
            await apiRequest(
                "/products",
                {
                    method: "GET",
                },
            );

        renderCards(products);

    } catch (error) {
        if (
            error instanceof ApiError &&
            error.status === 401
        ) {
            window.location.replace(
                "/login",
            );

            return;
        }

        console.error(
            "Unable to load cards:",
            error,
        );

        showError(t("cards.load_error"));
    }
}


async function initializeCards() {
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
            "cards",
        );

        cardsPage.hidden = false;

        await loadCards();

        await initializeGuidedTour(
            customer,
        );

    } catch (error) {
        console.error(
            "Unable to initialize cards:",
            error,
        );

        window.location.replace(
            "/login",
        );
    }
}


dialogCancel.addEventListener(
    "click",
    closeStatusDialog,
);


dialogConfirm.addEventListener(
    "click",
    changeCardStatus,
);


statusDialog.addEventListener(
    "click",
    (event) => {
        if (event.target === statusDialog) {
            closeStatusDialog();
        }
    },
);


statusDialog.addEventListener(
    "cancel",
    (event) => {
        event.preventDefault();
        closeStatusDialog();
    },
);


initializeCards();
