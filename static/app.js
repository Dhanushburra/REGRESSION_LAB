async function post(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body || {})
  });
  const text = await res.text();
  let data = null;
  try { data = JSON.parse(text); } catch (e) {}
  if (!res.ok) throw new Error((data && data.detail) || text || res.statusText);
  return data;
}

async function get(url) {
  const res = await fetch(url);
  const text = await res.text();
  let data = null;
  try { data = JSON.parse(text); } catch (e) {}
  if (!res.ok) throw new Error((data && data.detail) || text || res.statusText);
  return data;
}

document.getElementById("seedBtn").onclick = async () => {
  try {
    const out = await post("/api/dev/seed/", { customers: 200, orders_per_customer: 8, items_per_order: 4 });
    alert("Seeded: " + JSON.stringify(out));
  } catch (e) {
    alert("Seed failed: " + e.message);
  }
};

document.getElementById("cancelBtn").onclick = async () => {
  const id = document.getElementById("orderId").value.trim();
  const msg = document.getElementById("cancelMsg");
  msg.textContent = "";
  if (!id) { msg.textContent = "Enter an order id."; return; }
  try {
    const out = await post(`/api/orders/${id}/cancel/`, {});
    msg.textContent = "Cancelled: " + JSON.stringify(out);
  } catch (e) {
    msg.textContent = "Error: " + e.message;
    msg.className = "danger";
  }
};

document.getElementById("summaryBtn").onclick = async () => {
  const outEl = document.getElementById("summaryOut");
  const errEl = document.getElementById("summaryErr");
  outEl.textContent = "";
  errEl.textContent = "";
  const t0 = performance.now();
  try {
    const out = await get("/api/orders/summary/?limit=50");
    const t1 = performance.now();
    outEl.textContent = JSON.stringify({ ms: Math.round(t1 - t0), ...out }, null, 2);
  } catch (e) {
    errEl.textContent = e.message;
  }
};

document.getElementById("customerOrdersBtn").onclick = async () => {
  const id = document.getElementById("customerId").value.trim();
  const outEl = document.getElementById("customerOrdersOut");
  const errEl = document.getElementById("customerOrdersErr");
  outEl.textContent = "";
  errEl.textContent = "";
  console.log("Fetching orders for customer id:", id);
  
  if (!id) { 
    errEl.textContent = "Enter a customer id."; 
    return; 
  }
  
  try {
    const out = await get(`/api/customers/${id}/orders/`);
    outEl.textContent = JSON.stringify(out, null, 2);
  } catch (e) {
    errEl.textContent = e.message;
  }
};