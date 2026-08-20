// Runs inside the job advert's page and returns its text.
//
// Job boards are the single most common reason OfferPrinter fails: LinkedIn,
// Workday and Greenhouse render adverts with JavaScript behind a login, so a
// server-side fetch gets a shell or a 403. But the advert is already rendered
// in a tab you have open — so read it from there instead of fighting for it.
//
// Same order of preference as the Python fetcher, for consistency:
//   1. schema.org JobPosting JSON-LD, when the page publishes it.
//   2. The largest plausible content block.
//   3. Whatever the user has selected by hand.
(() => {
  const MIN_USEFUL = 200;

  function stripHtml(fragment) {
    const holder = document.createElement("div");
    holder.innerHTML = fragment
      .replace(/<(br|\/p|\/li|\/div|\/h[1-6])\s*\/?>/gi, "\n")
      .replace(/<li[^>]*>/gi, "- ");
    return tidy(holder.textContent || "");
  }

  function tidy(text) {
    return text
      .split("\n")
      .map((line) => line.replace(/[ \t ]+/g, " ").trim())
      .filter((line, index, all) => line || all[index - 1])
      .join("\n")
      .replace(/\n{3,}/g, "\n\n")
      .trim();
  }

  // 1. Structured data — the advert exactly as the employer's ATS published it.
  function fromJsonLd() {
    const walk = (node, out) => {
      if (Array.isArray(node)) {
        node.forEach((item) => walk(item, out));
      } else if (node && typeof node === "object") {
        out.push(node);
        Object.values(node).forEach((value) => walk(value, out));
      }
      return out;
    };

    for (const script of document.querySelectorAll('script[type="application/ld+json"]')) {
      let payload;
      try {
        payload = JSON.parse(script.textContent);
      } catch {
        continue;
      }
      for (const node of walk(payload, [])) {
        const types = [].concat(node["@type"] || []);
        if (!types.some((t) => String(t).toLowerCase() === "jobposting")) continue;
        const description = stripHtml(String(node.description || ""));
        if (description.length < MIN_USEFUL) continue;
        const org = node.hiringOrganization;
        return {
          text: description,
          company: (org && org.name) || (typeof org === "string" ? org : ""),
          role: node.title || "",
          source: "structured data",
        };
      }
    }
    return null;
  }

  // 2. The densest block of text on the page that isn't navigation.
  function fromDom() {
    const candidates = [
      ...document.querySelectorAll(
        "[class*='job'],[id*='job'],[class*='description'],[id*='description'],article,main,[role='main']"
      ),
    ];
    let best = null;
    let bestLength = 0;
    for (const element of candidates) {
      const clone = element.cloneNode(true);
      clone
        .querySelectorAll("script,style,noscript,nav,header,footer,svg,form,button")
        .forEach((n) => n.remove());
      // Go through innerHTML, not innerText: a detached clone has no layout, so
      // innerText degrades to textContent and every block runs together on one
      // line. stripHtml turns the block tags into real line breaks.
      const text = stripHtml(clone.innerHTML);
      if (text.length > bestLength) {
        best = text;
        bestLength = text.length;
      }
    }
    if (bestLength >= MIN_USEFUL) return { text: best, company: "", role: "", source: "page content" };

    // The live body does have layout, so innerText is right here.
    const body = tidy(document.body.innerText || "");
    return body.length >= MIN_USEFUL
      ? { text: body, company: "", role: "", source: "whole page" }
      : null;
  }

  // 3. Whatever the user highlighted — always right when they bothered to select.
  const selection = tidy(String(window.getSelection() || ""));
  if (selection.length >= MIN_USEFUL) {
    return { text: selection, company: "", role: "", source: "your selection" };
  }

  return fromJsonLd() || fromDom() || null;
})();
