import { ApiError, apiRequest } from "../api.js";
import { requireCustomer } from "../auth.js";
import { clearCart, emitStoreMetric, readCart, updateCartItem } from "../components/store-cart.js";
import {
    formatCurrency,
    i18nReady,
    t,
    translateValue,
} from "../i18n.js?v=1";

await i18nReady;

const page = document.querySelector("#cart-page");
const emptyState = document.querySelector("#cart-empty");
const checkoutLayout = document.querySelector("#cart-checkout");
const itemsContainer = document.querySelector("#cart-items");
const cardSelect = document.querySelector("#checkout-card");
const totalElement = document.querySelector("#cart-total");
const checkoutButton = document.querySelector("#checkout-button");
const errorElement = document.querySelector("#cart-error");
const receipt = document.querySelector("#receipt");
let catalog = new Map();

function money(value) {
    return formatCurrency(value);
}

function currentItems() {
    return Object.entries(readCart()).map(([productId, quantity]) => ({
        product_id: productId,
        quantity,
    }));
}

function total() {
    return currentItems().reduce(
        (sum, item) => sum + (catalog.get(item.product_id)?.price || 0) * item.quantity,
        0,
    );
}

function renderCart() {
    const storedItems = currentItems();
    storedItems
        .filter((item) => !catalog.has(item.product_id))
        .forEach((item) => updateCartItem(item.product_id, 0));
    const items = storedItems.filter((item) => catalog.has(item.product_id));
    emptyState.hidden = items.length > 0;
    checkoutLayout.hidden = items.length === 0;
    itemsContainer.replaceChildren(...items.map((item) => {
        const product = catalog.get(item.product_id);
        const row = document.createElement("article");
        row.className = "cart-item";
        row.innerHTML = `<span class="cart-item-emoji" aria-hidden="true"></span><div><h3></h3><span></span></div><div><label>Qty <select></select></label><button class="remove-item" type="button">Remove</button></div>`;
        row.querySelector(".cart-item-emoji").textContent = product.emoji;
        row.querySelector("h3").textContent = translateValue(product.name);
        row.querySelector("div > span").textContent = money(product.price * item.quantity);
        const quantity = row.querySelector("select");
        quantity.setAttribute("aria-label", t("store.quantity_for", {
            name: translateValue(product.name),
        }));
        for (let value = 1; value <= 10; value += 1) {
            const option = document.createElement("option");
            option.value = String(value); option.textContent = String(value); option.selected = value === item.quantity;
            quantity.append(option);
        }
        quantity.addEventListener("change", () => { updateCartItem(item.product_id, Number(quantity.value)); renderCart(); });
        row.querySelector("button").addEventListener("click", () => { updateCartItem(item.product_id, 0); renderCart(); });
        return row;
    }));
    totalElement.textContent = money(total());
}

function renderCards(cards) {
    cardSelect.replaceChildren();
    const creditCards = cards.filter((card) => card.product_type.toLowerCase().includes("card"));
    creditCards.forEach((card) => {
        const option = document.createElement("option");
        option.value = card.product_id;
        option.textContent = `${translateValue(card.product_type)} •••• ${card.last_four} — ${translateValue(card.product_status)}`;
        option.disabled = card.product_status !== "Active";
        cardSelect.append(option);
    });
    if (!creditCards.some((card) => card.product_status === "Active")) {
        checkoutButton.disabled = true;
        errorElement.textContent = t("store.no_card");
        errorElement.hidden = false;
    }
}

async function checkout() {
    errorElement.hidden = true;
    checkoutButton.disabled = true;
    checkoutButton.textContent = t("store.processing");
    const startedAt = performance.now();
    try {
        const result = await apiRequest("/store/checkout", {
            method: "POST",
            body: JSON.stringify({ card_product_id: cardSelect.value, items: currentItems() }),
        });
        clearCart();
        checkoutLayout.hidden = true;
        receipt.hidden = false;
        document.querySelector("#receipt-message").textContent = t("store.order_message");
        document.querySelector("#receipt-total").textContent = t("store.receipt", {
            count: result.item_count,
            total: money(result.total),
            order: result.order_id,
        });
        emitStoreMetric("checkout_completed", { basket_value: result.total, duration_ms: Math.round(performance.now() - startedAt) });
    } catch (requestError) {
        errorElement.textContent = requestError instanceof ApiError
            ? translateValue(requestError.message)
            : t("store.checkout_request_error");
        errorElement.hidden = false;
        checkoutButton.disabled = false;
        checkoutButton.textContent = t("store.place_order");
        emitStoreMetric("checkout_failed", { status: requestError.status || "network" });
    }
}

async function initialize() {
    const customer = await requireCustomer();
    if (!customer) return;
    page.hidden = false;
    try {
        const [products, cards] = await Promise.all([
            apiRequest("/store/products", { method: "GET" }),
            apiRequest("/products", { method: "GET" }),
        ]);
        catalog = new Map(products.map((product) => [product.product_id, product]));
        renderCards(cards);
        renderCart();
        emitStoreMetric("cart_viewed", { item_count: currentItems().length });
    } catch (requestError) {
        console.error("Unable to initialize checkout:", requestError);
        errorElement.textContent = t("store.checkout_error");
        errorElement.hidden = false;
    }
}

checkoutButton.addEventListener("click", checkout);
initialize();
