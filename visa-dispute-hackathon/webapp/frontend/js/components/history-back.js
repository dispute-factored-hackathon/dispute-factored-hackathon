const backLink = document.querySelector("[data-history-back]");

if (backLink) {
    backLink.addEventListener("click", (event) => {
        if (
            event.defaultPrevented
            || event.button !== 0
            || event.metaKey
            || event.ctrlKey
            || event.shiftKey
            || event.altKey
        ) {
            return;
        }

        // The store receipt deliberately sends customers to their newly created
        // transactions. From there, the bank back arrow must leave the store journey
        // and use its safe /home href instead of replaying browser history.
        if (new URLSearchParams(window.location.search).get("return") === "home") {
            return;
        }

        // Keep direct links and external referrers inside Factored Bank. When the customer came
        // from another application page, preserve their real navigation path instead of forcing
        // every back arrow to /home or a hard-coded list page.
        if (!document.referrer) return;
        const previous = new URL(document.referrer);
        if (previous.origin !== window.location.origin) return;
        if (previous.href === window.location.href) return;

        event.preventDefault();
        window.history.back();
    });
}
