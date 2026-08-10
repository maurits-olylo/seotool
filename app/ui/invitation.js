const token = new URLSearchParams(window.location.search).get("token");
const message = document.querySelector("#invitation-message");
let invitationRole = null;

async function loadInvitation() {
  if (!token) { message.textContent = "Deze uitnodigingslink is ongeldig."; return; }
  const response = await fetch(`/api/v1/invitations/${encodeURIComponent(token)}`);
  if (!response.ok) {
    message.textContent = "Deze uitnodigingslink is ongeldig, verlopen of al gebruikt.";
    return;
  }
  const invitation = await response.json();
  invitationRole = invitation.role;
  document.querySelector("#invitation-email").textContent = invitation.email;
}

document.querySelector("#invitation-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!token) { message.textContent = "Deze uitnodigingslink is ongeldig."; return; }
  const button = event.currentTarget.querySelector("button");
  button.disabled = true;
  message.className = "error";
  message.textContent = "Account wordt geactiveerd…";
  const response = await fetch(`/api/v1/invitations/${encodeURIComponent(token)}/accept`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({password: document.querySelector("#new-password").value}),
  });
  if (response.ok) {
    message.className = "success";
    message.textContent = "Account is geactiveerd. Je wordt nu ingelogd…";
    const destination = invitationRole === "admin" ? "/app#instellingen/klanten-websites" : "/app";
    window.setTimeout(() => window.location.assign(destination), 900);
    return;
  }
  const payload = await response.json().catch(() => ({}));
  const detail = Array.isArray(payload.detail)
    ? payload.detail.map((item) => item.msg).join(" ")
    : payload.detail;
  message.textContent = detail || "Activeren is mislukt.";
  button.disabled = false;
});

loadInvitation();
