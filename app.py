"""OfferPrinter WebUI — a clean Streamlit app.

Run with:  streamlit run app.py

Paste or upload your CV, paste a job description or its URL, pick a provider,
and click "Print my application". Each artifact streams in with its own download
buttons. Everything runs locally with your own API key.
"""

from __future__ import annotations

import io
import zipfile

import streamlit as st

from offerprinter.config import load_config
from offerprinter.controllers.pipeline import Pipeline
from offerprinter.models.schemas import Locale, Provider
from offerprinter.services.cv_parser import cv_from_text, extract_cv_from_bytes
from offerprinter.services.jd_fetcher import load_job_description
from offerprinter.services.writer import _combined_markdown

st.set_page_config(page_title="OfferPrinter", page_icon="🖨", layout="centered")


# --- sidebar: provider + settings ------------------------------------------


def sidebar_config():
    st.sidebar.header("⚙️ Settings")
    cfg = load_config()

    providers = [p.value for p in Provider]
    provider = st.sidebar.selectbox(
        "Provider", providers, index=providers.index(cfg.llm.provider.value)
    )
    model = st.sidebar.text_input("Model (blank = provider default)", value=cfg.llm.model)
    api_key = st.sidebar.text_input(
        "API key",
        value=cfg.llm.api_key,
        type="password",
        help="Used only to call your chosen provider. Never stored or sent anywhere else.",
    )
    locale = st.sidebar.radio(
        "English",
        [Locale.UK.value, Locale.US.value],
        index=0 if cfg.output.locale == Locale.UK else 1,
        horizontal=True,
    )

    st.sidebar.caption("Local-first & private: nothing leaves your machine except the LLM call.")

    cfg.llm.provider = Provider(provider)
    cfg.llm.model = model
    cfg.llm.api_key = api_key
    cfg.output.locale = Locale(locale)
    return cfg


# --- main -------------------------------------------------------------------


def main():
    st.title("🖨 OfferPrinter")
    st.markdown(
        "**Paste one job description and your CV. Get a complete, tailored "
        "application package — with zero fabrication.**"
    )

    cfg = sidebar_config()

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Your CV")
        cv_file = st.file_uploader(
            "Upload CV (.pdf, .docx, .md, .txt)", type=["pdf", "docx", "md", "txt"]
        )
        cv_text = st.text_area(
            "…or paste your CV", height=200, placeholder="Paste your CV text here"
        )
    with col2:
        st.subheader("The Job")
        jd_value = st.text_area(
            "Paste the job description, or a URL to fetch",
            height=260,
            placeholder="Paste the JD text, or https://careers.example.com/123",
        )

    go = st.button("🖨  Print my application", type="primary", use_container_width=True)

    if not go:
        return

    # --- validate inputs ---
    if not cv_file and not cv_text.strip():
        st.error("Please upload or paste your CV.")
        return
    if not jd_value.strip():
        st.error("Please paste a job description or a URL.")
        return
    if not cfg.llm.api_key:
        st.error(f"Please add an API key for {cfg.llm.provider.value} in the sidebar.")
        return

    # --- load inputs ---
    try:
        if cv_file is not None:
            resume = extract_cv_from_bytes(cv_file.getvalue(), cv_file.name)
        else:
            resume = cv_from_text(cv_text)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Could not read CV: {exc}")
        return

    try:
        with st.spinner("Loading job description…"):
            job = load_job_description(jd_value, timeout=cfg.llm.timeout)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Could not load job description: {exc}")
        return

    # --- run pipeline, streaming artifacts ---
    pipeline = Pipeline(cfg)
    progress = st.progress(0.0, text="Starting…")
    total = max(len(cfg.generation.enabled()), 1)
    done = 0
    package = None

    try:
        for event in pipeline.stream(resume, job):
            if event.kind == "meta":
                st.success(f"🎯 Target: **{event.message}**")
            elif event.kind == "artifact":
                done += 1
                progress.progress(done / total, text=f"Generated: {event.message}")
                art = event.artifact
                with st.expander(f"📄 {art.title}", expanded=(done == 1)):
                    st.markdown(art.content)
                    dcol1, dcol2 = st.columns(2)
                    dcol1.download_button(
                        "⬇ Markdown",
                        art.content,
                        file_name=f"{art.filename}.md",
                        mime="text/markdown",
                        key=f"md-{art.key}",
                    )
                    dcol2.download_button(
                        "⬇ Word (.docx)",
                        _artifact_docx_bytes(art),
                        file_name=f"{art.filename}.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        key=f"docx-{art.key}",
                    )
            elif event.kind == "written":
                package = event.package
                st.info(f"💾 Also saved to: `{event.message}`")
            elif event.kind == "done":
                package = event.package
    except Exception as exc:  # noqa: BLE001
        st.error(f"Generation failed: {exc}")
        return

    progress.progress(1.0, text="Done")

    # --- combined download ---
    if package:
        combined_md = _combined_markdown(package)
        st.download_button(
            "⬇ Download the full package (Markdown)",
            combined_md,
            file_name=f"{package.slug}-full-package.md",
            mime="text/markdown",
            use_container_width=True,
        )
        st.download_button(
            "⬇ Download everything as a .zip",
            _zip_bytes(package),
            file_name=f"{package.slug}.zip",
            mime="application/zip",
            use_container_width=True,
        )
        st.caption(
            "Every line is drawn from your real CV — nothing is fabricated. Review before sending."
        )


def _artifact_docx_bytes(artifact) -> bytes:
    """Render one artifact to .docx in memory for a download button."""
    import re

    from docx import Document

    from offerprinter.services.writer import _add_markdown_runs

    doc = Document()
    for raw_line in artifact.content.splitlines():
        line = raw_line.rstrip()
        if not line:
            doc.add_paragraph()
        elif line.startswith("### "):
            doc.add_heading(line[4:], level=3)
        elif line.startswith("## "):
            doc.add_heading(line[3:], level=2)
        elif line.startswith("# "):
            doc.add_heading(line[2:], level=1)
        elif line.lstrip().startswith(("- ", "* ")):
            _add_markdown_runs(doc.add_paragraph(style="List Bullet"), line.lstrip()[2:])
        elif re.match(r"^\d+\.\s", line.lstrip()):
            _add_markdown_runs(
                doc.add_paragraph(style="List Number"), re.sub(r"^\d+\.\s", "", line.lstrip())
            )
        else:
            _add_markdown_runs(doc.add_paragraph(), line)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _zip_bytes(package) -> bytes:
    """Bundle every artifact (Markdown) plus the combined file into a zip."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for art in package.artifacts:
            zf.writestr(f"{art.filename}.md", art.content.rstrip() + "\n")
        zf.writestr("full-package.md", _combined_markdown(package))
    return buf.getvalue()


if __name__ == "__main__":
    main()
