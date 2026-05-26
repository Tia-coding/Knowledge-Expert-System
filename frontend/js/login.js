/**
 * Login Page - NRSC Authentication
 * Secure login with role selection and input validation
 */

const loginForm = document.querySelector("#loginForm");
const usernameInput = document.querySelector("#username");
const passwordInput = document.querySelector("#password");
const roleSelect = document.querySelector("#loginRole");

// ============================================================
// Form Validation
// ============================================================

function validateLoginForm() {
  const username = usernameInput.value.trim();
  const password = passwordInput.value.trim();
  const role = roleSelect.value.toLowerCase();

  if (!username) {
    toast("Please enter your username");
    usernameInput.focus();
    return false;
  }

  if (username.length < 3) {
    toast("Username must be at least 3 characters");
    usernameInput.focus();
    return false;
  }

  if (!password) {
    toast("Please enter your password");
    passwordInput.focus();
    return false;
  }

  if (password.length < 6) {
    toast("Password must be at least 6 characters");
    passwordInput.focus();
    return false;
  }

  if (role !== "administrator" && role !== "user") {
    toast("Please select a valid role");
    roleSelect.focus();
    return false;
  }

  return true;
}

// ============================================================
// Form Submission
// ============================================================

loginForm.addEventListener("submit", async event => {
  event.preventDefault();

  if (!validateLoginForm()) {
    return;
  }

  const username = usernameInput.value.trim();
  const password = passwordInput.value.trim();
  const requestedRole = roleSelect.value.toLowerCase() === "administrator" ? "admin" : "user";

  const button = event.submitter;
  button.disabled = true;
  const originalText = button.textContent;
  button.innerHTML = '<span class="spinner"></span> Signing in...';

  try {
    const response = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password, role: requestedRole })
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.detail || "Invalid credentials");
    }

    // Verify role matches requested role (critical security check)
    if (!data.role || data.role.toLowerCase() !== requestedRole.toLowerCase()) {
      throw new Error("Authentication role mismatch. Access denied.");
    }

    // Store authentication tokens securely
    localStorage.setItem("nrsc_token", data.access_token);
    localStorage.setItem("nrsc_role", data.role);
    localStorage.setItem("nrsc_username", data.username);

    // Redirect based on authenticated role
    toast("Login successful!");
    setTimeout(() => {
      const redirectUrl = data.role === "admin" ? "/admin.html" : "/user.html";
      location.href = redirectUrl;
    }, 300);

  } catch (error) {
    console.error("Login error:", error);
    toast("Login failed: " + (error.message || "Invalid credentials"));
    button.disabled = false;
    button.textContent = originalText;
  }
});

// ============================================================
// Real-time Input Validation
// ============================================================

usernameInput.addEventListener("blur", () => {
  const value = usernameInput.value.trim();
  if (value && value.length < 3) {
    usernameInput.style.borderColor = "var(--danger)";
  } else {
    usernameInput.style.borderColor = "";
  }
});

passwordInput.addEventListener("blur", () => {
  const value = passwordInput.value.trim();
  if (value && value.length < 6) {
    passwordInput.style.borderColor = "var(--danger)";
  } else {
    passwordInput.style.borderColor = "";
  }
});

// Clear error styling on input
usernameInput.addEventListener("input", () => {
  usernameInput.style.borderColor = "";
});

passwordInput.addEventListener("input", () => {
  passwordInput.style.borderColor = "";
});

// ============================================================
// Enter Key Navigation
// ============================================================

usernameInput.addEventListener("keypress", event => {
  if (event.key === "Enter") {
    passwordInput.focus();
  }
});

passwordInput.addEventListener("keypress", event => {
  if (event.key === "Enter") {
    loginForm.requestSubmit();
  }
});

// ============================================================
// Focus on Load
// ============================================================

window.addEventListener("load", () => {
  usernameInput.focus();
});
