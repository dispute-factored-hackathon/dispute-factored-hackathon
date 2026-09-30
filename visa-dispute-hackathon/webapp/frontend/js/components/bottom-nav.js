const NAVIGATION_ITEMS = [
    {
        href: "/home",
        label: "Home",
        icon: "⌂",
        key: "home",
    },
    {
        href: "/cards",
        label: "Cards",
        icon: "◫",
        key: "cards",
    },
    {
        href: "/transactions",
        label: "Activity",
        icon: "↕",
        key: "transactions",
    },
    {
        href: "/agent",
        label: "Izzy",
        icon: "✦",
        key: "agent",
    },
];


export function renderBottomNavigation(
    element,
    currentPage,
) {
    if (!element) {
        return;
    }

    element.replaceChildren();

    for (const item of NAVIGATION_ITEMS) {
        const link =
            document.createElement("a");

        link.className =
            "bottom-nav-link";

        link.href = item.href;

        if (item.key === currentPage) {
            link.setAttribute(
                "aria-current",
                "page",
            );
        }

        const icon =
            document.createElement("span");

        icon.className =
            "bottom-nav-icon";

        icon.setAttribute(
            "aria-hidden",
            "true",
        );

        icon.textContent = item.icon;

        const label =
            document.createElement("span");

        label.textContent = item.label;

        link.append(
            icon,
            label,
        );

        element.append(link);
    }
}
