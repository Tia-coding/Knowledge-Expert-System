const API_BASE = "/api";

function token() {
  return localStorage.getItem("nrsc_token");
}

function authHeaders() {
  return { Authorization: `Bearer ${token()}` };
}

async function api(path, options = {}) {
  const headers = options.body instanceof FormData
    ? { ...(options.headers || {}), ...authHeaders() }
    : { "Content-Type": "application/json", ...(options.headers || {}), ...authHeaders() };
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  
  if (response.status === 401 || response.status === 403) {
    // Unauthorized - clear all tokens and redirect to login
    clearAuthSession();
    location.href = "/index.html";
    return;
  }
  
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(error.detail || "Request failed");
  }
  return response.json();
}

function clearAuthSession() {
  // Clear all authentication data
  localStorage.removeItem("nrsc_token");
  localStorage.removeItem("nrsc_role");
  localStorage.removeItem("nrsc_username");
  sessionStorage.clear();
}

function toast(message) {
  const el = document.querySelector("#toast");
  if (!el) return;
  el.textContent = message;
  el.classList.add("show");
  setTimeout(() => el.classList.remove("show"), 2800);
}

function logout() {
  clearAuthSession();
  location.href = "/index.html";
}

function guard(role) {
  if (!token()) {
    location.href = "/index.html";
    return;
  }
  
  const currentRole = localStorage.getItem("nrsc_role");
  
  // If role is specified, verify it matches (case-insensitive)
  if (role && currentRole && currentRole.toLowerCase() !== role.toLowerCase()) {
    clearAuthSession();
    location.href = "/index.html";
    return;
  }
  
  // If role is specified but currentRole is missing, redirect to login
  if (role && !currentRole) {
    clearAuthSession();
    location.href = "/index.html";
    return;
  }
}

function setActive(section) {
  document.querySelectorAll(".section").forEach(el => el.classList.remove("active"));
  document.querySelector(`#${section}`)?.classList.add("active");
  document.querySelectorAll(".nav-item").forEach(el => {
    el.classList.toggle("active", el.dataset.section === section);
  });
}