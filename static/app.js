// Prevent double submissions (each submit can trigger an AI call and a saved report).
document.addEventListener("submit", function (event) {
    var form = event.target;
    if (!form.matches || !form.matches("[data-loading-form]")) { return; }
    var button = form.querySelector("button[type=submit]");
    if (button) {
        button.disabled = true;
        button.textContent = button.getAttribute("data-loading-text") || "Please wait...";
    }
});
