import { t } from "../i18n.js?v=1";

const NAVIGATION_ITEMS = [
    {
        href: "/home",
        labelKey: "nav.home",
        icon: "<path d='M3 10.5 12 3l9 7.5'/><path d='M5 9.5V21h14V9.5'/><path d='M9 21v-7h6v7'/>",
        key: "home",
    },
    {
        href: "/cards",
        labelKey: "nav.cards",
        icon: "<rect x='3' y='5' width='18' height='14' rx='2'/><path d='M3 10h18'/>",
        key: "cards",
    },
    {
        href: "/transactions",
        labelKey: "nav.transactions",
        icon: "<path d='M7 7h13M7 12h13M7 17h13'/><path d='m3 7 1 1 2-2M3 12l1 1 2-2M3 17l1 1 2-2'/>",
        key: "transactions",
    },
    {
        href: "/agent",
        labelKey: "nav.izzy",
        icon: "<path d='m12 3 1.4 4.6L18 9l-4.6 1.4L12 15l-1.4-4.6L6 9l4.6-1.4L12 3Z'/><path d='m19 15 .7 2.3L22 18l-2.3.7L19 21l-.7-2.3L16 18l2.3-.7L19 15Z'/>",
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

        const icon = document.createElement("span");

        icon.className =
            "bottom-nav-icon";

        icon.setAttribute(
            "aria-hidden",
            "true",
        );

        icon.innerHTML = `<svg viewBox="0 0 24 24" focusable="false">${item.icon}</svg>`;

        const label =
            document.createElement("span");

        label.textContent = t(item.labelKey);

        link.append(
            icon,
            label,
        );

        element.append(link);
    }
}
