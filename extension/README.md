# 🖨 OfferPrinter browser extension

Grabs a job description from the tab you are looking at and hands it to the CLI.

## Why this exists

Fetching a job advert by URL fails more often than anything else OfferPrinter
does. LinkedIn, Workday and most big ATS platforms render adverts with
JavaScript, sit behind a login, or block anything that isn't a browser. No
amount of clever scraping fixes that.

But the advert is already on your screen. This reads it from there.

## Install

Chrome, Edge, Brave, Arc — anything Chromium:

1. Go to `chrome://extensions`
2. Turn on **Developer mode** (top right)
3. **Load unpacked** → select this `extension/` folder

## Use

1. Open the job advert.
2. Click the OfferPrinter icon → **Copy for OfferPrinter**.
3. Run:

```bash
offerprinter --cv ~/cv.pdf --jd-clipboard
```

Or **Save as .txt** and use `--jd-file`, which is handier when you are
collecting a batch to run through `offerprinter rank --jd-dir`.

If a page defeats it, select the advert text by hand first — a selection always
wins over automatic extraction.

## How it extracts

Same order of preference as the Python fetcher:

1. **Your selection**, if you made one.
2. **schema.org `JobPosting` JSON-LD** — the advert as the employer's own ATS
   published it, which is cleaner than anything scraped from the DOM and comes
   with the company and job title attached.
3. **The densest content block** on the page, with nav, headers, footers,
   forms and buttons stripped.

## Privacy

The extension has **no host permissions and makes no network requests**. It
cannot talk to a server because it has no way to reach one. It reads the tab
only when you click the button (`activeTab`), and the text goes to your
clipboard or your downloads folder — nowhere else.

That is the same bargain as the rest of OfferPrinter: your data goes to the LLM
provider you chose, and to nobody else.
