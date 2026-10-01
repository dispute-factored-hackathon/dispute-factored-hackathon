const CART_KEY = "shady_business_cart";

export function readCart() {
    try {
        const parsed = JSON.parse(sessionStorage.getItem(CART_KEY) || "{}");
        if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
        return Object.fromEntries(
            Object.entries(parsed).filter(
                ([productId, quantity]) => productId && Number.isInteger(quantity) && quantity > 0,
            ),
        );
    } catch {
        return {};
    }
}

export function writeCart(cart) {
    sessionStorage.setItem(CART_KEY, JSON.stringify(cart));
    window.dispatchEvent(new CustomEvent("shady:cart-updated", { detail: cart }));
}

export function addToCart(productId, quantity = 1) {
    const cart = readCart();
    cart[productId] = Math.min(10, (cart[productId] || 0) + quantity);
    writeCart(cart);
}

export function updateCartItem(productId, quantity) {
    const cart = readCart();
    if (quantity <= 0) delete cart[productId];
    else cart[productId] = Math.min(10, quantity);
    writeCart(cart);
}

export function clearCart() {
    writeCart({});
}

export function cartCount() {
    return Object.values(readCart()).reduce((total, quantity) => total + quantity, 0);
}

export function updateCartBadges() {
    const count = cartCount();
    document.querySelectorAll("[data-cart-count]").forEach((badge) => {
        badge.textContent = String(count);
        badge.hidden = count === 0;
    });
}

function pointerOrigin(event, sourceElement) {
    if (event?.clientX || event?.clientY) return { x: event.clientX, y: event.clientY };
    const bounds = sourceElement.getBoundingClientRect();
    return { x: bounds.left + bounds.width / 2, y: bounds.top + bounds.height / 2 };
}

function createClickBurst(origin) {
    const burst = document.createElement("span");
    burst.className = "cart-click-burst";
    burst.style.left = `${origin.x}px`;
    burst.style.top = `${origin.y}px`;
    burst.setAttribute("aria-hidden", "true");
    burst.innerHTML = Array.from({ length: 8 }, (_, index) =>
        `<i style="--spark-angle:${index * 45}deg"></i>`,
    ).join("");
    document.body.append(burst);
    burst.addEventListener("animationend", () => burst.remove(), { once: true });
}

function flyToCart(sourceElement, emoji, cartLink) {
    const source = sourceElement.getBoundingClientRect();
    const destination = cartLink.getBoundingClientRect();
    const flyer = document.createElement("span");
    flyer.className = "cart-flyer";
    flyer.textContent = emoji;
    flyer.setAttribute("aria-hidden", "true");
    flyer.style.left = `${source.left + source.width / 2}px`;
    flyer.style.top = `${source.top + source.height / 2}px`;
    flyer.style.setProperty("--cart-x", `${destination.left + destination.width / 2 - source.left - source.width / 2}px`);
    flyer.style.setProperty("--cart-y", `${destination.top + destination.height / 2 - source.top - source.height / 2}px`);
    flyer.style.setProperty("--cart-mid-x", `${(destination.left + destination.width / 2 - source.left - source.width / 2) * 0.45}px`);
    flyer.style.setProperty("--cart-mid-y", `${(destination.top + destination.height / 2 - source.top - source.height / 2) * 0.2}px`);
    document.body.append(flyer);
    flyer.addEventListener("animationend", () => flyer.remove(), { once: true });
}

export function animateAddToCart({ event, sourceElement, emoji }) {
    const cartLink = document.querySelector(".cart-link");
    if (!sourceElement || !cartLink) return Promise.resolve();

    cartLink.classList.remove("cart-link-confirmed");
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
        cartLink.classList.add("cart-link-confirmed");
        return Promise.resolve();
    }

    createClickBurst(pointerOrigin(event, sourceElement));
    flyToCart(sourceElement, emoji, cartLink);
    window.setTimeout(() => cartLink.classList.add("cart-link-confirmed"), 520);
    return new Promise((resolve) => window.setTimeout(resolve, 720));
}

export function emitStoreMetric(name, detail = {}) {
    window.dispatchEvent(new CustomEvent("shady:store-metric", { detail: { name, ...detail } }));
}
