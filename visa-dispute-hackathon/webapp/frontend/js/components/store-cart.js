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

export function emitStoreMetric(name, detail = {}) {
    window.dispatchEvent(new CustomEvent("shady:store-metric", { detail: { name, ...detail } }));
}
