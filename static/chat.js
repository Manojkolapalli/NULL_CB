const form = document.querySelector("#chat-form");
const input = document.querySelector("#message-input");
const sendButton = document.querySelector("#send-button");
const messagesElement = document.querySelector("#messages");
const welcome = document.querySelector("#welcome");

const conversation = [];

function addMessage(role, content, extraClass = "") {
  const message = document.createElement("div");
  message.className = `message ${role}${extraClass ? ` ${extraClass}` : ""}`;
  if (role === "assistant" && window.marked && window.DOMPurify) {
    message.classList.add("markdown");
    const markdown = content.replace(
      /^\s*```(?:markdown|md)\s*\r?\n([\s\S]*?)\r?\n```\s*$/i,
      "$1",
    );
    message.innerHTML = window.DOMPurify.sanitize(window.marked.parse(markdown));
  } else {
    message.textContent = content;
  }
  messagesElement.append(message);
  message.scrollIntoView({ behavior: "smooth", block: "end" });
  return message;
}

function resizeInput() {
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 180)}px`;
}

input.addEventListener("input", resizeInput);
input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = input.value.trim();
  if (!text || sendButton.disabled) return;

  welcome.hidden = true;
  conversation.push({ role: "user", content: text });
  addMessage("user", text);
  input.value = "";
  resizeInput();
  input.disabled = true;
  sendButton.disabled = true;
  const loadingMessage = addMessage("assistant", "NULL is thinking...", "loading");

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: conversation }),
    });
    let data = null;
    try {
      data = await response.json();
    } catch {
      // Non-JSON responses are reported below with their HTTP status.
    }
    if (!response.ok) {
      const detail = typeof data?.error === "string"
        ? data.error
        : `The request failed (HTTP ${response.status}${response.statusText ? ` ${response.statusText}` : ""}).`;
      throw new Error(detail);
    }
    if (data === null || typeof data.reply !== "string" || !data.reply.trim()) {
      throw new Error("The AI returned an empty response. Please try again.");
    }

    loadingMessage.remove();
    conversation.push({ role: "assistant", content: data.reply });
    addMessage("assistant", data.reply);
  } catch (error) {
    loadingMessage.remove();
    conversation.pop();
    const message = error instanceof TypeError
      ? "Could not reach the NULL server. Start the Flask app and open the chat at http://127.0.0.1:5000/."
      : error instanceof Error
        ? error.message
        : "Something went wrong. Please try again.";
    addMessage("assistant", message, "error");
  } finally {
    input.disabled = false;
    sendButton.disabled = false;
    input.focus();
  }
});
