# Deploying OfferPrinter

Four ways to put OfferPrinter in front of people, from "one click" to "runs in
your own cloud". All of them are optional — the tool is designed to run on a
laptop first.

Because the web UI falls back to **demo mode** when no API key is configured, a
public deployment is safe: strangers see the bundled example package and can
paste their own key in the sidebar if they want to print something real. You
never pay for their runs, and you never hold their key.

---

## 1. Streamlit Community Cloud (easiest, free)

The fastest way to get a public URL.

1. Push this repository to your GitHub account.
2. Go to <https://share.streamlit.io> and sign in with GitHub.
3. **New app** → pick this repo, branch `main`, main file `app.py`.
4. Deploy. That's it — `.streamlit/config.toml` in this repo already sets the
   theme and disables usage stats.

**Do not** add an API key to the app's secrets unless you intend to pay for
every visitor's runs. Leaving it unset is what enables demo mode.

If you *do* want a key-backed public demo, set a spend limit on the provider
account first, and add it under **Settings → Secrets**:

```toml
ANTHROPIC_API_KEY = "sk-ant-..."
OFFERPRINTER_TRACK = "false"   # don't write history in an ephemeral container
```

---

## 2. Hugging Face Spaces (free, good for discovery)

Spaces has real search traffic for AI tools, which makes it worth the ten
minutes.

1. Create a new Space at <https://huggingface.co/new-space>, SDK **Streamlit**.
2. Push this repository to it, or add the Space as a second git remote.
3. Copy `deploy/huggingface/README.md` to the repository root **in the Space
   only** — Spaces reads its configuration from the README front-matter.

The Space config is kept in `deploy/huggingface/README.md` so it does not
collide with this project's own README.

---

## 3. Docker (anywhere that runs containers)

A multi-arch image is published to the GitHub Container Registry on every push
to `main` and every tag:

```bash
docker run --rm -p 8501:8501 \
  -e ANTHROPIC_API_KEY="sk-ant-..." \
  ghcr.io/mohitagw15856/offerprinter:latest
```

Then open <http://localhost:8501>.

To run the CLI from the image instead of the web UI:

```bash
docker run --rm -v "$PWD:/work" -w /work \
  -e ANTHROPIC_API_KEY="sk-ant-..." \
  ghcr.io/mohitagw15856/offerprinter:latest \
  offerprinter --cv my-cv.pdf --jd-file jd.txt
```

To build it yourself, `docker compose up` uses the local `Dockerfile`.

---

## 4. Fly.io / Railway / Render

Any platform that can run a Dockerfile will run OfferPrinter unchanged. The
only things to set:

| Setting | Value |
|---|---|
| Port | `8501` |
| Command | `streamlit run app.py --server.address=0.0.0.0 --server.port=8501` |
| Health check | `GET /_stcore/health` |
| Memory | 512MB is plenty |

Set `OFFERPRINTER_TRACK=false` on any ephemeral host so the tracker doesn't try
to write history into a container that is about to disappear.

---

## A note on privacy when hosting

OfferPrinter is local-first by design, and hosting it moves one specific thing:
your visitors' CVs now pass through **your** server on the way to the LLM
provider. Nothing is written to disk unless `OFFERPRINTER_TRACK` is on, and
nothing is logged — but if you run a public instance, say so plainly on the
page. The whole product is built on being straight with people.
