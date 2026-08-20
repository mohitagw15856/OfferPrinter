"""An MCP server, so agents can drive OfferPrinter directly.

`docs/skill/SKILL.md` already tells an agent how to shell out to the CLI. This
goes further: it exposes the same operations as Model Context Protocol tools, so
Claude Desktop, Claude Code and anything else speaking MCP can call them
natively and get **structured** results back — a fit score as a number, gaps as
a list, findings as objects — rather than parsing prose out of a terminal.

    offerprinter mcp

The protocol here is JSON-RPC 2.0 over newline-delimited stdin/stdout. That is
implemented by hand rather than by adding an SDK dependency, for the same reason
this project writes its own PDFs: the surface actually needed is small, and a
lean dependency tree installs fast and breaks rarely.

Everything is subject to the same no-fabrication rules as the CLI, and every
tool result includes the verification summary so an agent cannot present the
output as checked when it is not.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from typing import Any

from offerprinter import __version__
from offerprinter.config import Config, load_config
from offerprinter.controllers.pipeline import Pipeline
from offerprinter.models.schemas import ResumeInput
from offerprinter.services.cv_parser import cv_from_text, extract_cv
from offerprinter.services.jd_fetcher import load_job_description
from offerprinter.services.ranker import Ranker, collect_jobs, sort_results

#: The MCP revision this server implements.
PROTOCOL_VERSION = "2025-06-18"

_CV_INPUT = {
    "cv_path": {
        "type": "string",
        "description": "Path to the candidate's CV (.pdf, .docx, .md, .txt).",
    },
    "cv_text": {
        "type": "string",
        "description": "The CV as plain text, if you do not have a file path.",
    },
}
_JD_INPUT = {
    "job_description": {
        "type": "string",
        "description": "The job description as text, or a URL to fetch.",
    },
}


def _resume_from(arguments: dict) -> ResumeInput:
    if arguments.get("cv_text"):
        return cv_from_text(arguments["cv_text"])
    if arguments.get("cv_path"):
        return extract_cv(arguments["cv_path"])
    raise ValueError("Provide either cv_path or cv_text — never invent a CV.")


class OfferPrinterMCP:
    """A minimal MCP server exposing OfferPrinter's operations."""

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or load_config()
        self.tools: dict[str, tuple[dict, Callable[[dict], dict]]] = {}
        self._register_tools()

    # -- tool definitions ---------------------------------------------------

    def _register_tools(self) -> None:
        self.tools["print_application_package"] = (
            {
                "name": "print_application_package",
                "description": (
                    "Generate a complete tailored job-application package from a CV and a "
                    "job description: tailored CV, cover letter, fit memo, ATS keyword "
                    "report and interview prep pack, plus a 0-100 fit score. Never invents "
                    "experience; gaps are reported, not filled in. Returns the fit score, "
                    "the gaps, the fabrication-check result and the output directory."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        **_CV_INPUT,
                        **_JD_INPUT,
                        "output_dir": {
                            "type": "string",
                            "description": "Where to write the package. Defaults to ./output.",
                        },
                    },
                    "required": ["job_description"],
                },
            },
            self._tool_print_package,
        )

        self.tools["score_fit"] = (
            {
                "name": "score_fit",
                "description": (
                    "Score how well a CV matches one job description, 0-100, with a band, "
                    "genuine strengths and genuine gaps. Two cheap calls, no documents "
                    "written. Use this to triage before generating anything."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {**_CV_INPUT, **_JD_INPUT},
                    "required": ["job_description"],
                },
            },
            self._tool_score_fit,
        )

        self.tools["rank_jobs"] = (
            {
                "name": "rank_jobs",
                "description": (
                    "Score many job descriptions against one CV and return them ranked by "
                    "fit, best first. Accepts a folder of .txt/.md adverts and/or a list of "
                    "URLs. Writes nothing."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        **_CV_INPUT,
                        "directory": {
                            "type": "string",
                            "description": "Folder containing .txt/.md job descriptions.",
                        },
                        "urls": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Job advert URLs to fetch and score.",
                        },
                    },
                },
            },
            self._tool_rank_jobs,
        )

        self.tools["roast_cv"] = (
            {
                "name": "roast_cv",
                "description": (
                    "Blunt, funny, opt-in critique of a CV's writing — clichés, vague "
                    "claims, unquantified bullets — ending with the five edits that would "
                    "most change the outcome. Critiques the writing, never the person."
                ),
                "inputSchema": {"type": "object", "properties": dict(_CV_INPUT)},
            },
            self._tool_roast,
        )

    # -- tool implementations ----------------------------------------------

    def _pipeline(self, output_dir: str | None = None) -> Pipeline:
        config = load_config()
        if output_dir:
            config.output.dir = output_dir
        return Pipeline(config)

    def _tool_print_package(self, arguments: dict) -> dict:
        resume = _resume_from(arguments)
        jd = load_job_description(arguments["job_description"])
        pipeline = self._pipeline(arguments.get("output_dir"))
        package = pipeline.run(resume, jd)

        result: dict[str, Any] = {
            "company": package.company,
            "role": package.role,
            "output_dir": f"{pipeline.config.output.dir}/{package.slug}",
            "artifacts": [a.filename for a in package.artifacts],
            "tokens": package.usage.total_tokens,
            "cost_usd": round(package.usage.cost_usd, 4),
        }
        if package.fit:
            result["fit"] = {
                "score": package.fit.score,
                "band": package.fit.band,
                "strengths": package.fit.strengths,
                "gaps": package.fit.gaps,
            }
        if package.verification:
            result["fabrication_check"] = {
                "passed": package.verification.passed,
                "summary": package.verification.summary(),
                "findings": [
                    {
                        "claim": f.claim,
                        "severity": f.severity.value,
                        "reason": f.reason,
                        "artifact": f.artifact,
                    }
                    for f in package.verification.findings
                ],
            }
        return result

    def _tool_score_fit(self, arguments: dict) -> dict:
        resume = _resume_from(arguments)
        jd = load_job_description(arguments["job_description"])
        pipeline = self._pipeline()
        company, role = pipeline.generator.extract_meta(jd)
        fit = pipeline.generator.score_fit(resume, jd, company, role)
        return {
            "company": company,
            "role": role,
            "score": fit.score,
            "band": fit.band,
            "verdict": fit.verdict,
            "strengths": fit.strengths,
            "gaps": fit.gaps,
        }

    def _tool_rank_jobs(self, arguments: dict) -> dict:
        from pathlib import Path

        resume = _resume_from(arguments)
        directory = arguments.get("directory")
        jobs = collect_jobs(
            directory=Path(directory) if directory else None,
            urls=arguments.get("urls") or [],
        )
        if not jobs:
            raise ValueError("No job descriptions found — pass `directory` and/or `urls`.")

        pipeline = self._pipeline()
        ranker = Ranker(pipeline.generator, max_workers=pipeline.config.generation.max_workers)
        results = [progress.result for progress in ranker.rank(resume, jobs)]

        return {
            "ranked": [
                {
                    "source": r.source,
                    "company": r.company,
                    "role": r.role,
                    "score": r.score,
                    "band": r.fit.band if r.fit else "",
                    "gaps": r.fit.gaps if r.fit else [],
                    "error": r.error,
                }
                for r in sort_results(results)
            ]
        }

    def _tool_roast(self, arguments: dict) -> dict:
        resume = _resume_from(arguments)
        artifact = self._pipeline().generator.roast(resume)
        return {"roast": artifact.content}

    # -- JSON-RPC plumbing --------------------------------------------------

    def handle(self, message: dict) -> dict | None:
        """Handle one JSON-RPC message. Returns None for notifications."""
        method = message.get("method")
        request_id = message.get("id")
        params = message.get("params") or {}

        # Notifications carry no id and expect no reply.
        if request_id is None:
            return None

        try:
            result = self._dispatch(method, params)
        except Exception as exc:  # noqa: BLE001 - every failure becomes an RPC error
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32603, "message": str(exc)},
            }
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def _dispatch(self, method: str | None, params: dict) -> dict:
        if method == "initialize":
            return {
                "protocolVersion": params.get("protocolVersion") or PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "offerprinter", "version": __version__},
                "instructions": (
                    "OfferPrinter turns one CV and one job description into a tailored "
                    "application package, and never invents experience the candidate does "
                    "not have. Always pass the user's real CV — never write one yourself. "
                    "Surface the fit score, the gaps and the fabrication check when you "
                    "report results; those are the most useful parts, not the least."
                ),
            }

        if method == "ping":
            return {}

        if method == "tools/list":
            return {"tools": [definition for definition, _ in self.tools.values()]}

        if method == "tools/call":
            name = params.get("name")
            if name not in self.tools:
                raise ValueError(f"Unknown tool: {name}")
            _, handler = self.tools[name]
            payload = handler(params.get("arguments") or {})
            return {
                "content": [{"type": "text", "text": json.dumps(payload, indent=2)}],
                "structuredContent": payload,
                "isError": False,
            }

        raise ValueError(f"Unknown method: {method}")

    def serve(self, stdin=None, stdout=None) -> None:
        """Read newline-delimited JSON-RPC from stdin until EOF."""
        stdin = stdin or sys.stdin
        stdout = stdout or sys.stdout

        for line in stdin:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                response = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": "Parse error"},
                }
            else:
                response = self.handle(message)
                if response is None:
                    continue

            stdout.write(json.dumps(response) + "\n")
            stdout.flush()


def main() -> None:
    """Entry point for `offerprinter mcp`."""
    OfferPrinterMCP().serve()


if __name__ == "__main__":
    main()
