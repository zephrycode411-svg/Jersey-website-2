const adminTokenKey = "dej-admin-token";
const adminLoginSection = document.getElementById("adminLoginSection");
const adminDashboard = document.getElementById("adminDashboard");
const adminMessage = document.getElementById("adminMessage");
const dashboardMessage = document.getElementById("dashboardMessage");

function escapeAdminHtml(value) {
  return String(value).replace(/[&<>"']/g, character => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
  })[character]);
}

async function adminRequest(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-Admin-Token": sessionStorage.getItem(adminTokenKey) || "",
      ...options.headers
    }
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(result.error || `Request failed (${response.status}).`);
  return result;
}

async function loadAdminData() {
  dashboardMessage.textContent = "Loading store data...";
  try {
    const [products, orders] = await Promise.all([
      adminRequest("/api/admin/products"),
      adminRequest("/api/admin/orders")
    ]);
    renderInventory(products);
    renderOrders(orders);
    adminLoginSection.hidden = true;
    adminDashboard.hidden = false;
    dashboardMessage.textContent = "Store data loaded.";
  } catch (error) {
    sessionStorage.removeItem(adminTokenKey);
    adminLoginSection.hidden = false;
    adminDashboard.hidden = true;
    adminMessage.textContent = error.message;
  }
}

function renderInventory(products) {
  document.getElementById("inventoryList").innerHTML = products.map(product => `
    <details class="admin-product" data-product-id="${escapeAdminHtml(product.id)}">
      <summary>
        <span><strong>${escapeAdminHtml(product.name)}</strong><small>${escapeAdminHtml(product.sku)} · ${escapeAdminHtml(product.team)}</small></span>
        <span>${product.stockTracked ? "Stock tracked" : "Untracked"}</span>
      </summary>
      <div class="admin-product-body">
        <div class="stock-inputs">
          ${["S", "L", "XL", "XXL"].map(size => `
            <label>${size}<input type="number" min="0" step="1" data-stock-size="${size}" value="${product.stockBySize[size] ?? ""}" placeholder="Untracked"></label>
          `).join("")}
        </div>
        <button class="btn save-stock-button" type="button">SAVE STOCK</button>
      </div>
    </details>
  `).join("");
}

function renderOrders(orders) {
  const container = document.getElementById("ordersList");
  if (!orders.length) {
    container.innerHTML = '<p class="admin-help">No order requests have been recorded yet.</p>';
    return;
  }

  container.innerHTML = orders.map(order => `
    <details class="admin-order" data-order-reference="${escapeAdminHtml(order.reference)}">
      <summary>
        <span><strong>${escapeAdminHtml(order.reference)}</strong><small>${escapeAdminHtml(order.customer_name)} · ${new Date(order.created_at).toLocaleString()}</small></span>
        <span class="order-status">${escapeAdminHtml(order.status.replaceAll("_", " "))}</span>
      </summary>
      <div class="admin-order-body">
        <p>${escapeAdminHtml(order.customer_phone)}</p>
        <p>${escapeAdminHtml(order.delivery_address)}</p>
        <ul>${order.items.map(item => `<li>${escapeAdminHtml(item.product_name)} · ${escapeAdminHtml(item.size)} × ${item.quantity}${item.badge !== "none" ? ` · ${escapeAdminHtml(item.badge)}${item.badge_text ? ` (${escapeAdminHtml(item.badge_text)})` : ""}` : ""}</li>`).join("")}</ul>
        <strong>Subtotal: ₦${Number(order.subtotal).toLocaleString("en-NG")}</strong>
        <div class="order-status-controls">
          <label for="status-${escapeAdminHtml(order.reference)}">Update status</label>
          <select id="status-${escapeAdminHtml(order.reference)}" class="order-status-select">
            ${["pending_confirmation", "confirmed", "dispatched", "completed", "cancelled"].map(status => `<option value="${status}" ${order.status === status ? "selected" : ""}>${status.replaceAll("_", " ")}</option>`).join("")}
          </select>
          <button class="btn save-order-button" type="button">UPDATE</button>
        </div>
      </div>
    </details>
  `).join("");
}

document.getElementById("adminLoginForm").addEventListener("submit", async event => {
  event.preventDefault();
  sessionStorage.setItem(adminTokenKey, document.getElementById("adminToken").value);
  await loadAdminData();
});

document.getElementById("adminSignOut").addEventListener("click", () => {
  sessionStorage.removeItem(adminTokenKey);
  adminDashboard.hidden = true;
  adminLoginSection.hidden = false;
  document.getElementById("adminToken").value = "";
  adminMessage.textContent = "Signed out.";
});

document.getElementById("refreshAdmin").addEventListener("click", loadAdminData);

document.getElementById("inventoryList").addEventListener("click", async event => {
  const button = event.target.closest(".save-stock-button");
  if (!button) return;
  const product = button.closest(".admin-product");
  const stock = {};
  for (const input of product.querySelectorAll("[data-stock-size]")) {
    const value = input.value.trim();
    if (value && (!Number.isInteger(Number(value)) || Number(value) < 0)) {
      dashboardMessage.textContent = "Stock must be a whole number of 0 or more, or left blank.";
      input.focus();
      return;
    }
    stock[input.dataset.stockSize] = value === "" ? null : Number(value);
  }

  button.disabled = true;
  try {
    await adminRequest(`/api/admin/products/${encodeURIComponent(product.dataset.productId)}/stock`, {
      method: "PATCH",
      body: JSON.stringify({ stock })
    });
    dashboardMessage.textContent = "Stock saved.";
    await loadAdminData();
  } catch (error) {
    dashboardMessage.textContent = error.message;
    button.disabled = false;
  }
});

document.getElementById("ordersList").addEventListener("click", async event => {
  const button = event.target.closest(".save-order-button");
  if (!button) return;
  const order = button.closest(".admin-order");
  const status = order.querySelector(".order-status-select").value;
  button.disabled = true;
  try {
    await adminRequest(`/api/admin/orders/${encodeURIComponent(order.dataset.orderReference)}`, {
      method: "PATCH",
      body: JSON.stringify({ status })
    });
    dashboardMessage.textContent = "Order status updated.";
    await loadAdminData();
  } catch (error) {
    dashboardMessage.textContent = error.message;
    button.disabled = false;
  }
});

if (sessionStorage.getItem(adminTokenKey)) loadAdminData();