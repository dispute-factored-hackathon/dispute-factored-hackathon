import {
    ApiError,
    apiRequest,
} from "../api.js";

import {
    requireCustomer,
} from "../auth.js";

import {
    renderBottomNavigation,
} from "../components/bottom-nav.js?v=2";

import {
    initializeGuidedTour,
} from "../components/guided-tour.js";


const page =
    document.querySelector("#complaint-page");

const detail =
    document.querySelector("#complaint-detail");

const pageError =
    document.querySelector("#page-error");

const profileInitial =
    document.querySelector("#profile-initial");

const complaintStatus =
    document.querySelector("#complaint-status");

const complaintCategory =
    document.querySelector("#complaint-category");

const complaintSubcategory =
    document.querySelector("#complaint-subcategory");

const claimedAmount =
    document.querySelector("#claimed-amount");

const complaintDescription =
    document.querySelector("#complaint-description");

const creationDate =
    document.querySelector("#creation-date");

const caseType =
    document.querySelector("#case-type");

const complaintPriority =
    document.querySelector("#complaint-priority");

const receptionChannel =
    document.querySelector("#reception-channel");

const firstResponseDate =
    document.querySelector("#first-response-date");

const slaStatus =
    document.querySelector("#sla-status");

const resolutionStatus =
    document.querySelector("#resolution-status");

const resolutionText =
    document.querySelector("#resolution-text");

const resolutionDetails =
    document.querySelector("#resolution-details");

const resolutionDate =
    document.querySelector("#resolution-date");

const resolutionDays =
    document.querySelector("#resolution-days");

const compensation =
    document.querySelector("#compensation");

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
    if (
        amount === null
        || amount === undefined
    ) {
        return "—";
    }

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
    if (!value) {
        return "—";
    }

    return new Intl.DateTimeFormat(
        undefined,
        {
            dateStyle: "medium",
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


function complaintIdFromPath() {
    const parts =
        window.location.pathname
            .split("/")
            .filter(Boolean);

    if (
        parts.length !== 2
        || parts[0] !== "complaints"
    ) {
        return null;
    }

    return decodeURIComponent(
        parts[1],
    );
}


function renderResolution(
    complaint,
) {
    if (!complaint.resolution) {
        resolutionStatus.textContent =
            "This complaint is still being processed.";

        resolutionText.textContent =
            "No final resolution has been recorded yet.";

        resolutionDetails.hidden = true;

        return;
    }

    resolutionStatus.textContent =
        "This complaint has been resolved.";

    resolutionText.textContent =
        complaint.resolution;

    resolutionDate.textContent =
        formatDate(
            complaint.resolution_date,
        );

    resolutionDays.textContent =
        complaint.resolution_days === null
            ? "—"
            : `${complaint.resolution_days} days`;

    compensation.textContent =
        formatMoney(
            complaint.compensation_granted,
            complaint.currency,
        );

    resolutionDetails.hidden = false;
}


function renderComplaint(
    complaint,
) {
    complaintStatus.textContent =
        complaint.status;

    complaintStatus.className =
        `status-badge ${
            statusClass(
                complaint.status,
            )
        }`;

    complaintCategory.textContent =
        complaint.category;

    complaintSubcategory.textContent =
        complaint.subcategory
        || complaint.case_type;

    claimedAmount.textContent =
        formatMoney(
            complaint.claimed_amount,
            complaint.currency,
        );

    complaintDescription.textContent =
        complaint.description;

    creationDate.textContent =
        formatDate(
            complaint.creation_date,
        );

    caseType.textContent =
        complaint.case_type;

    complaintPriority.textContent =
        complaint.priority;

    receptionChannel.textContent =
        complaint.reception_channel;

    firstResponseDate.textContent =
        formatDate(
            complaint.first_response_date,
        );

    slaStatus.textContent =
        complaint.sla_breached
            ? "SLA breached"
            : "Within SLA";

    renderResolution(
        complaint,
    );

    detail.hidden = false;
}


async function loadComplaint(
    complaintId,
) {
    try {
        const complaint =
            await apiRequest(
                `/complaints/${encodeURIComponent(
                    complaintId,
                )}`,
                {
                    method: "GET",
                },
            );

        renderComplaint(
            complaint,
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
                "We couldn't find this complaint.",
            );

            return;
        }

        console.error(
            "Unable to load complaint:",
            error,
        );

        showError(
            "We could not load this complaint. "
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
            null,
        );

        page.hidden = false;

        const complaintId =
            complaintIdFromPath();

        if (!complaintId) {
            showError(
                "Invalid complaint.",
            );

            return;
        }

        await loadComplaint(
            complaintId,
        );

        await initializeGuidedTour();

    } catch (error) {
        console.error(
            "Unable to initialize complaint:",
            error,
        );

        window.location.replace(
            "/login",
        );
    }
}


initialize();
