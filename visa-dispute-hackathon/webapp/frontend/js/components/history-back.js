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
