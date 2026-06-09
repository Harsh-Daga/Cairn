"""Minimal OpenAPI 3 specification for the Cairn HTTP API."""

from __future__ import annotations

from typing import Any


def openapi_spec() -> dict[str, Any]:
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "Cairn API",
            "version": "1.0.0",
            "description": "Local-first inference workspace HTTP API",
        },
        "paths": {
            "/v1/projects/{project_id}/sessions": {
                "get": {
                    "summary": "List capture sessions",
                    "parameters": [
                        {
                            "name": "project_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {"200": {"description": "Session list"}},
                }
            },
            "/v1/sessions/{session_id}": {
                "get": {
                    "summary": "Get capture session",
                    "parameters": [
                        {
                            "name": "session_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {"200": {"description": "Session detail"}},
                }
            },
            "/v1/sessions/{session_id}/events": {
                "get": {
                    "summary": "Stream session events (SSE)",
                    "parameters": [
                        {
                            "name": "session_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {"200": {"description": "text/event-stream"}},
                }
            },
            "/v1/workflows/{workflow_id}/run": {
                "post": {
                    "summary": "Execute a workflow",
                    "parameters": [
                        {
                            "name": "workflow_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {"200": {"description": "Workflow run result"}},
                }
            },
            "/v1/runs/{run_id}/report": {
                "get": {
                    "summary": "Unified observability report for a run",
                    "parameters": [
                        {
                            "name": "run_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {"200": {"description": "Unified report JSON"}},
                }
            },
        },
    }
