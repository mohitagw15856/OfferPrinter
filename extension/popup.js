// Popup logic: pull the advert out of the active tab, then hand it to the CLI
// via the clipboard (or a file). The extension deliberately never talks to a
// server — it has no host permissions and nothing to send anywhere.

const statusEl = document.getElementById("status");
const metaEl = document.getElementById("meta");
const hintEl = document.getElementById("hint");

function say(message, className = "") {
  statusEl.textContent = message;
  statusEl.className = className;
}

async function grab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab) throw new Error("No active tab.");

  const [result] = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    files: ["extract.js"],
  });

  const found = result && result.result;
  if (!found || !found.text) {
    throw new Error("Couldn't find the advert. Select the text by hand and try again.");
  }
  return { ...found, url: tab.url };
}

function describe(found) {
  const words = found.text.split(/\s+/).length;
  const bits = [`${words.toLocaleString()} words`, `via ${found.source}`];
  if (found.role) bits.unshift(found.role);
  if (found.company) bits.splice(1, 0, found.company);
  return bits.join(" · ");
}

document.getElementById("copy").addEventListener("click", async () => {
  say("Reading the page…");
  try {
    const found = await grab();
    await navigator.clipboard.writeText(found.text);
    say("Copied. Now run the command below.", "ok");
    metaEl.textContent = describe(found);
    hintEl.hidden = false;
  } catch (error) {
    say(error.message, "warn");
  }
});

document.getElementById("download").addEventListener("click", async () => {
  say("Reading the page…");
  try {
    const found = await grab();
    const slug = (found.role || "job-description")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "");
    const blob = new Blob([found.text], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    await chrome.downloads.download({ url, filename: `${slug || "job-description"}.txt` });
    say("Saved to your downloads.", "ok");
    metaEl.textContent = describe(found);
  } catch (error) {
    // `downloads` is an optional permission; fall back to copying instead.
    say(`${error.message} — try Copy instead.`, "warn");
  }
});
