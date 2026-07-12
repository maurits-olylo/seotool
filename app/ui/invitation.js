document.querySelector("#invitation-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = document.querySelector("#invitation-message");
  const token = new URLSearchParams(window.location.search).get("token");
  if (!token) { message.textContent = "Deze uitnodigingslink is ongeldig."; return; }
  const response = await fetch(`/api/v1/invitations/${encodeURIComponent(token)}/accept`, {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({display_name: document.querySelector("#display-name").value, password: document.querySelector("#new-password").value}),
  });
  if (response.ok) { window.location.assign("/login"); return; }
  const payload = await response.json().catch(() => ({}));
  message.textContent = payload.detail || "Activeren is mislukt.";
});
