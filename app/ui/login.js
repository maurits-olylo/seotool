document.querySelector("#team-login").addEventListener("submit", async (event) => {
  event.preventDefault();
  const error = document.querySelector("#login-error");
  const button = event.currentTarget.querySelector("button");
  error.textContent = ""; button.disabled = true; button.textContent = "Inloggen…";
  const response = await fetch("/ui/login", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({email: document.querySelector("#email").value, password: document.querySelector("#password").value}),
  });
  if (response.ok) { window.location.assign("/app"); return; }
  const payload = await response.json().catch(() => ({}));
  error.textContent = payload.detail || "Inloggen is mislukt.";
  button.disabled = false; button.textContent = "Inloggen";
});
