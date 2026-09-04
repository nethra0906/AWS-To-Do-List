"use strict";

/**
 * Frontend for the serverless to-do list.
 * Talks to the API Gateway + Lambda backend defined in lambda_function.py.
 *
 * All task text is rendered via textContent (never innerHTML), so
 * user-entered task text can never be interpreted as HTML/script.
 */

const API_BASE_URL = (typeof APP_CONFIG !== "undefined" && APP_CONFIG.API_BASE_URL) || "";
const MAX_TASK_LENGTH = 500;

const form = document.getElementById("taskForm");
const input = document.getElementById("taskInput");
const addBtn = document.getElementById("addBtn");
const list = document.getElementById("taskList");
const statusRegion = document.getElementById("statusRegion");
const taskCountEl = document.getElementById("taskCount");
const clearCompletedBtn = document.getElementById("clearCompletedBtn");
const filterButtons = Array.from(document.querySelectorAll(".filter-btn"));
const datelineEl = document.getElementById("dateline");

if (datelineEl) {
  datelineEl.textContent = new Date().toLocaleDateString(undefined, {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

/** @type {Array<{taskId: string, task: string, status: string}>} */
let tasks = [];
let currentFilter = "all"; // "all" | "active" | "done"
let isLoading = false;

function announce(message) {
  statusRegion.textContent = message;
}

function setBusy(busy) {
  addBtn.disabled = busy;
  input.disabled = busy;
}

async function apiRequest(method, body) {
  if (!API_BASE_URL) {
    throw new Error("API_BASE_URL is not configured. Edit config.js first.");
  }
  const res = await fetch(API_BASE_URL, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
    cache: "no-store",
  });

  let payload = null;
  const text = await res.text();
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      // Non-JSON response body; leave payload null and fall back to status text.
    }
  }

  if (!res.ok) {
    const message = (payload && payload.error) || `Request failed (${res.status})`;
    throw new Error(message);
  }
  return payload;
}

function renderLoading() {
  list.innerHTML = "";
  const li = document.createElement("li");
  li.className = "state-row";
  const cursor = document.createElement("span");
  cursor.className = "loading-cursor";
  cursor.setAttribute("aria-hidden", "true");
  li.append("Loading ", cursor);
  list.appendChild(li);
}

function renderMessage(message, { isError = false, showRetry = false } = {}) {
  list.innerHTML = "";
  const li = document.createElement("li");
  li.className = "state-row" + (isError ? " error" : "");
  li.append(message);
  if (showRetry) {
    const retryBtn = document.createElement("button");
    retryBtn.type = "button";
    retryBtn.className = "text-link";
    retryBtn.textContent = "Retry";
    retryBtn.addEventListener("click", loadTasks);
    li.appendChild(retryBtn);
  }
  list.appendChild(li);
}

function getFilteredTasks() {
  if (currentFilter === "active") return tasks.filter((t) => t.status !== "done");
  if (currentFilter === "done") return tasks.filter((t) => t.status === "done");
  return tasks;
}

function updateTaskCount() {
  const remaining = tasks.filter((t) => t.status !== "done").length;
  taskCountEl.textContent =
    tasks.length === 0
      ? "0 tasks"
      : `${remaining} of ${tasks.length} task${tasks.length === 1 ? "" : "s"} left`;
}

function render() {
  updateTaskCount();

  const visible = getFilteredTasks();
  list.innerHTML = "";

  if (tasks.length === 0) {
    renderMessage("No tasks yet. Add one above!");
    return;
  }
  if (visible.length === 0) {
    renderMessage(`No ${currentFilter} tasks.`);
    return;
  }

  visible.forEach((t, i) => {
    list.appendChild(buildTaskItem(t, i));
  });
}

function buildTaskItem(t, index) {
  const li = document.createElement("li");
  li.className = "task-row" + (t.status === "done" ? " done" : "");
  li.dataset.taskId = t.taskId;

  const indexSpan = document.createElement("span");
  indexSpan.className = "task-index";
  indexSpan.setAttribute("aria-hidden", "true");
  indexSpan.textContent = String(index + 1).padStart(2, "0");
  li.appendChild(indexSpan);

  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.className = "task-check";
  checkbox.checked = t.status === "done";
  checkbox.setAttribute("aria-label", t.status === "done" ? "Mark as not done" : "Mark as done");
  checkbox.addEventListener("change", () => toggleDone(t));
  li.appendChild(checkbox);

  const textSpan = document.createElement("span");
  textSpan.className = "task-text";
  textSpan.textContent = t.task;
  li.appendChild(textSpan);

  const links = document.createElement("div");
  links.className = "task-links";

  const editBtn = document.createElement("button");
  editBtn.type = "button";
  editBtn.className = "text-link";
  editBtn.setAttribute("aria-label", "Edit task");
  editBtn.textContent = "Edit";
  editBtn.addEventListener("click", () => startEdit(li, t));
  links.appendChild(editBtn);

  const deleteBtn = document.createElement("button");
  deleteBtn.type = "button";
  deleteBtn.className = "text-link danger";
  deleteBtn.setAttribute("aria-label", "Delete task");
  deleteBtn.textContent = "Delete";
  deleteBtn.addEventListener("click", () => deleteTask(t));
  links.appendChild(deleteBtn);

  li.appendChild(links);
  return li;
}

function startEdit(li, t) {
  const textSpan = li.querySelector(".task-text");
  const editInput = document.createElement("input");
  editInput.type = "text";
  editInput.className = "task-edit-input";
  editInput.maxLength = MAX_TASK_LENGTH;
  editInput.value = t.task;
  li.replaceChild(editInput, textSpan);
  editInput.focus();
  editInput.select();

  let settled = false;
  const commit = async () => {
    if (settled) return;
    settled = true;
    const newText = editInput.value.trim();
    if (!newText || newText === t.task) {
      render();
      return;
    }
    await updateTask(t, { task: newText });
  };
  const cancel = () => {
    if (settled) return;
    settled = true;
    render();
  };

  editInput.addEventListener("blur", commit);
  editInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      commit();
    } else if (e.key === "Escape") {
      e.preventDefault();
      cancel();
    }
  });
}

async function loadTasks() {
  isLoading = true;
  renderLoading();
  try {
    const data = await apiRequest("GET");
    tasks = Array.isArray(data) ? data : data.items || [];
    render();
  } catch (err) {
    console.error("Error loading tasks:", err);
    renderMessage(`Couldn't load tasks: ${err.message}`, { isError: true, showRetry: true });
  } finally {
    isLoading = false;
  }
}

async function handleAddSubmit(event) {
  event.preventDefault();
  const task = input.value.trim();
  if (!task) return;
  if (task.length > MAX_TASK_LENGTH) {
    announce(`Task is too long (max ${MAX_TASK_LENGTH} characters).`);
    return;
  }

  setBusy(true);
  try {
    const created = await apiRequest("POST", { task });
    tasks.push(created);
    input.value = "";
    render();
    announce("Task added.");
  } catch (err) {
    console.error("Error adding task:", err);
    announce(`Couldn't add task: ${err.message}`);
  } finally {
    setBusy(false);
    input.focus();
  }
}

async function toggleDone(t) {
  const newStatus = t.status === "done" ? "pending" : "done";
  await updateTask(t, { status: newStatus });
}

async function updateTask(t, changes) {
  const previous = { ...t };
  Object.assign(t, changes); // optimistic update
  render();
  try {
    await apiRequest("PUT", { taskId: t.taskId, ...changes });
    announce("Task updated.");
  } catch (err) {
    console.error("Error updating task:", err);
    Object.assign(t, previous); // roll back
    render();
    announce(`Couldn't update task: ${err.message}`);
  }
}

async function deleteTask(t) {
  const index = tasks.indexOf(t);
  if (index === -1) return;
  tasks.splice(index, 1);
  render();
  try {
    await apiRequest("DELETE", { taskId: t.taskId });
    announce("Task deleted.");
  } catch (err) {
    console.error("Error deleting task:", err);
    tasks.splice(index, 0, t); // roll back
    render();
    announce(`Couldn't delete task: ${err.message}`);
  }
}

async function clearCompleted() {
  const completed = tasks.filter((t) => t.status === "done");
  if (completed.length === 0) return;
  await Promise.all(completed.map((t) => deleteTask(t)));
}

function setFilter(filter) {
  currentFilter = filter;
  for (const btn of filterButtons) {
    btn.setAttribute("aria-pressed", btn.dataset.filter === filter ? "true" : "false");
  }
  render();
}

form.addEventListener("submit", handleAddSubmit);
clearCompletedBtn.addEventListener("click", clearCompleted);
for (const btn of filterButtons) {
  btn.addEventListener("click", () => setFilter(btn.dataset.filter));
}

loadTasks();
