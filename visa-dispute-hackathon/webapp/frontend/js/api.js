export class ApiError extends Error {
    constructor(
        message,
        status,
        details = null,
    ) {
        super(message);

        this.name = "ApiError";
        this.status = status;
        this.details = details;
    }
}


function validationMessage(detail) {
    if (!Array.isArray(detail)) {
        return null;
    }

    const messages = detail.map((error) => {
        const location = Array.isArray(error.loc)
            ? error.loc
                .filter((part) => part !== "body")
                .join(".")
            : "";

        const message =
            error.msg || "Invalid value";

        if (!location) {
            return message;
        }

        return `${location}: ${message}`;
    });

    return messages.join(" · ");
}


export async function apiRequest(
    path,
    options = {},
) {
    const response = await fetch(`/api${path}`, {
        credentials: "same-origin",

        ...options,

        headers: {
            "Content-Type": "application/json",
            ...(options.headers || {}),
        },
    });

    const contentType =
        response.headers.get("content-type") || "";

    let body = null;

    if (contentType.includes("application/json")) {
        body = await response.json();
    } else {
        const text = await response.text();

        if (text) {
            body = text;
        }
    }

    if (!response.ok) {
        let message =
            `Request failed with status ${response.status}.`;

        if (
            body &&
            typeof body === "object"
        ) {
            if (typeof body.detail === "string") {
                message = body.detail;
            } else {
                const validationError =
                    validationMessage(body.detail);

                if (validationError) {
                    message = validationError;
                }
            }
        } else if (
            typeof body === "string" &&
            body
        ) {
            message = body;
        }

        throw new ApiError(
            message,
            response.status,
            body,
        );
    }

    return body;
}
