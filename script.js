const API_URL = "https://eqpd6y86k1.execute-api.eu-north-1.amazonaws.com/prod";

async function loadTasks() {
  try {
    const res = await fetch(API_URL, { cache: "no-store" });
    if (!res.ok) throw new Error("Failed to fetch tasks");
    const data = await res.json();

    const tasks = Array.isArray(data) ? data : data.items || [];

    const list = document.getElementById("taskList");
    list.innerHTML = "";

    if (!tasks || tasks.length === 0) {
      list.innerHTML = "<li class='empty'>No tasks yet. Add one!</li>";
      return;
    }

    tasks.forEach((t) => {
      const li = document.createElement("li");
      li.innerHTML = `
        <span class="${t.status === "done" ? "done" : ""}">${t.task}</span>
        <div>
          <button onclick="markDone('${t.taskId}')">✔</button>
          <button onclick="deleteTask('${t.taskId}')">🗑</button>
        </div>`;
      list.appendChild(li);
    });
  } catch (err) {
    console.error("Error loading tasks:", err);
  }
}

async function addTask() {
  const input = document.getElementById("taskInput");
  const task = input.value.trim();
  if (!task) return alert("Enter a task!");

  console.log("Adding task:", task); 

  try {
    const res = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task }),
    });

    console.log("Response status:", res.status); 

    const text = await res.text(); 
    console.log("Raw response:", text); 

    if (!res.ok) throw new Error("Failed to add task");

    await loadTasks();
  } catch (err) {
    console.error("Error adding task:", err);
    alert("Could not add task. Check console for details.");
  }

  input.value = "";
}


async function markDone(id) {
  try {
    const res = await fetch(API_URL, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ taskId: id, status: "done" }),
    });
    if (!res.ok) throw new Error("Failed to mark done");
    await loadTasks();
  } catch (err) {
    console.error("Error marking done:", err);
  }
}

async function deleteTask(id) {
  try {
    const res = await fetch(API_URL, {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ taskId: id }),
    });
    if (!res.ok) throw new Error("Failed to delete task");
    await loadTasks();
  } catch (err) {
    console.error("Error deleting task:", err);
  }
}

loadTasks();
