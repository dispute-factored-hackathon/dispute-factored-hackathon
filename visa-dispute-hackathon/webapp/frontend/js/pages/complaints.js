import {
    ApiError,
    apiRequest,
} from "../api.js";
import {
    getLocale,
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


const page =
    document.querySelector("#complaints-page");

const list =
    document.querySelector("#complaints-list");

const emptyState =
    document.querySelector("#empty-state");

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
            getLocale(),
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
    return new Intl.DateTimeFormat(
        getLocale(),
        {
            month: "short",
            day: "numeric",
            year: "numeric",
        },
    ).format(
        new Date(value),
    );
}


function statusClass(status) {
    const normalized =
        status.toLowerCase();

    if (normalized === "resolved") {
        return "status-resolved";
    }

    if (
        normalized.includes("review")
        || normalized.includes("open")
        || normalized.includes("pending")
    ) {
        return "status-open";
    }

    return "status-default";
}


function createComplaintItem(
    complaint,
) {
    const item =
        document.createElement("a");

    item.className =
        "complaint-item";

    item.href =
        `/complaints/${encodeURIComponent(
            complaint.complaint_id,
        )}`;

    const main =
        document.createElement("div");

    const category =
        document.createElement("p");

    category.className =
        "complaint-category";

    category.textContent =
        complaint.category;

    const subcategory =
        document.createElement("p");

    subcategory.className =
        "complaint-subcategory";

    subcategory.textContent =
        complaint.subcategory
        || complaint.case_type;

    const meta =
        document.createElement("div");

    meta.className =
        "complaint-meta";

    const date =
        document.createElement("span");

    date.textContent =
        formatDate(
            complaint.creation_date,
        );

    const priority =
        document.createElement("span");

    priority.textContent = t("complaints.priority_value", {
        priority: translateValue(complaint.priority),
    });

    meta.append(
        date,
        document.createTextNode("·"),
        priority,
    );

    main.append(
        category,
        subcategory,
        meta,
    );

    const side =
        document.createElement("div");

    side.className =
        "complaint-side";

    const amount =
        document.createElement("span");

    amount.className =
        "complaint-amount";

    amount.textContent =
        formatMoney(
            complaint.claimed_amount,
            complaint.currency,
        );

    const status =
        document.createElement("span");

    status.className =
        `status-badge ${
            statusClass(
                complaint.status,
            )
        }`;

    status.textContent = translateValue(complaint.status);

    side.append(
        amount,
        status,
    );

    item.append(
        main,
        side,
    );

    return item;
}


function renderComplaints(
    complaints,
) {
    list.replaceChildren();

    if (complaints.length === 0) {
        emptyState.hidden = false;
        return;
    }

    emptyState.hidden = true;

    for (
        const complaint
        of complaints
    ) {
        list.append(
            createComplaintItem(
                complaint,
            ),
        );
    }
}


async function loadComplaints() {
    clearError();

    try {
        const complaints =
            await apiRequest(
                "/complaints",
                {
                    method: "GET",
                },
            );

        renderComplaints(
            complaints,
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
            "Unable to load complaints:",
            error,
        );

        showError(t("complaints.load_error"));
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
            null,
        );

        page.hidden = false;

        await loadComplaints();

        await initializeGuidedTour(
            customer,
        );

    } catch (error) {
        console.error(
            "Unable to initialize complaints:",
            error,
        );

        window.location.replace(
            "/login",
        );
    }
}


initialize();
