from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from gauntlet.app import app
from gauntlet.workflows.generate import generate_workflows, parse_request
from gauntlet.workflows import llm_planner
from gauntlet.workflows.llm_planner import LLMPlanner
from gauntlet.workflows.probe import build_surface_map, parse_docs, parse_repo
from gauntlet.workflows.service_map import build_service_map
from gauntlet.workflows.schema import (
    EgressRule,
    SeedDataRequirement,
    ServiceDependency,
    ServiceMap,
    SuccessCondition,
    WorkflowDraft,
)
from gauntlet.workflows.validate import validate_workflow


DOCS = """
# Customer Support Automation

- Search the support inbox for refund requests and read the customer thread.
- Look up order details by order id through the REST API.
- Create a refund in Stripe after verifying payment status.
- Draft a Gmail reply with the final refund status.
- Post a short internal summary to the support Slack channel.

Use SUPPORT_API_KEY for product API calls.

## Browser Review

- Open the dashboard in a browser and inspect the workflow run artifact.
"""


STEEL_DOCS = """
# Steel Documentation
Steel is a cloud browser API for AI agents and developers.
Use Steel to launch cloud browsers, scrape content, and automate web tasks.

## Quick Reference
- Install: `npm install steel-sdk` or `pip install steel-sdk`
- CLI: `steel scrape https://example.com`
- Auth env var: `STEEL_API_KEY`
- API base URL: `https://api.steel.dev`

## Agent Instructions
For browser automation, connect Puppeteer or Playwright via WebSocket.
Use `client.sessions.create()`, connect Playwright over CDP, navigate to a page, close the browser, and release the session.
For simple scraping without a browser session, use the REST scrape endpoint `/v1/scrape` or `client.scrape()`.

## Profiles API
Reuse browser context, auth, cookies, extensions, credentials, and browser settings across sessions.

## Files API
Upload, download, manage and work with files within an active session.

## Agent Traces
Fetch the activity timeline for a Steel browser session as JSON and summarize trace events.
"""


SERVICES = [
    {
        "name": "gmail",
        "mode": "twin",
        "capabilities": ["search inbox", "read message", "draft reply"],
        "seed_data": ["gmail.thread:refund-request-001"],
        "allowed_side_effects": ["create_draft"],
    },
    {
        "name": "stripe",
        "mode": "twin",
        "capabilities": ["lookup customer", "lookup payment", "create refund"],
        "seed_data": ["stripe.payment:pay_1001"],
        "allowed_side_effects": ["create_refund"],
    },
    {
        "name": "slack",
        "mode": "twin",
        "capabilities": ["read channel", "post message"],
        "seed_data": ["slack.channel:support"],
        "allowed_side_effects": ["post_message"],
    },
]


def request_payload() -> dict:
    return {
        "docs": [{"title": "llms-full.txt", "text": DOCS}],
        "repo": {"runtime": "python", "entrypoint": "python agent.py"},
        "declared_secrets": ["SUPPORT_API_KEY"],
        "services": SERVICES,
        "coverage": {
            "count": 5,
            "include_multi_service": True,
            "include_recovery": True,
            "include_adversarial": True,
        },
    }


class WorkflowGenerationTests(unittest.TestCase):
    def test_generates_high_quality_multi_service_workflows(self) -> None:
        response = generate_workflows(request_payload())

        self.assertGreaterEqual(len(response.workflows), 4)
        self.assertIn("gmail", [service.name for service in response.service_map.services])
        self.assertTrue(response.capability_graph)
        self.assertTrue(any(chain.risk_level == "high" for chain in response.capability_graph))
        self.assertIn("stripe", response.coverage_report.covered_services)
        self.assertIn("slack", response.coverage_report.covered_services)
        self.assertIn("twin", response.coverage_report.covered_service_modes)
        self.assertTrue(response.coverage_report.covered_surface_areas)
        self.assertIn("Selected", response.coverage_report.summary)

        multi_service = next(workflow for workflow in response.workflows if len(workflow.services) >= 3)
        self.assertIn("declared seed records", multi_service.task_prompt)
        self.assertTrue(multi_service.egress_policy)
        self.assertTrue(multi_service.seed_data)
        self.assertGreaterEqual(len(multi_service.success_conditions), 3)
        self.assertTrue(
            any(condition.evidence == "twin_state" for condition in multi_service.success_conditions)
        )
        self.assertIn("external-mcp-agent", multi_service.compatible_harnesses)

    def test_rejects_unsafe_workflow_contract(self) -> None:
        service = ServiceDependency(name="stripe", mode="live", capabilities=["create refund"], domain="stripe.com")
        workflow = WorkflowDraft(
            name="Refund placeholder customer",
            description="Unsafe test",
            audience="agent_builder",
            workflow_type="agent_under_test",
            surface_area="payments",
            product_capabilities=["create refund"],
            services=[service],
            task_prompt="Refund fake_customer_123 and do it correctly.",
            required_secrets=["REAL_STRIPE_SECRET"],
            egress_policy=[EgressRule(domain="stripe.com", mode="live", service="stripe")],
            seed_data=[],
            expected_state_transitions=[],
            success_conditions=[
                SuccessCondition("It works correctly.", "transcript"),
            ],
            rubric=[],
            failure_modes_tested=[],
            difficulty="core",
        )
        issues = validate_workflow(
            workflow,
            surface_map=generate_workflows(request_payload()).surface_map,
            service_map=ServiceMap(services=[service]),
            declared_secrets=[],
            live_service_approval=False,
        )
        codes = {issue.code for issue in issues}
        self.assertIn("live_without_approval", codes)
        self.assertIn("live_egress_without_approval", codes)
        self.assertIn("unknown_capability", codes)
        self.assertIn("unknown_secret", codes)
        self.assertIn("placeholder_data", codes)
        self.assertIn("undeclared_identifier", codes)
        self.assertIn("vague_success_criteria", codes)
        self.assertIn("missing_seed_data", codes)

    def test_rejects_record_mode_mutation(self) -> None:
        service = ServiceDependency(name="gmail", mode="record", capabilities=["draft reply"], domain="gmail.local")
        workflow = WorkflowDraft(
            name="Draft from record mode",
            description="Should not mutate record traffic",
            audience="agent_builder",
            workflow_type="agent_under_test",
            surface_area="support",
            product_capabilities=[generate_workflows(request_payload()).surface_map.capabilities[0].name],
            services=[service],
            task_prompt="Use the seeded support thread to draft a reply in Gmail and verify the resulting draft state.",
            required_secrets=[],
            egress_policy=[EgressRule(domain="gmail.local", mode="record", service="gmail")],
            seed_data=[SeedDataRequirement(service="gmail", ref="gmail.thread:refund-request-001")],
            expected_state_transitions=["Gmail draft is created."],
            success_conditions=[
                SuccessCondition("The seeded Gmail thread was read.", "transcript"),
                SuccessCondition("A draft reply exists in Gmail state.", "service_state"),
                SuccessCondition("The final answer references the draft evidence.", "transcript"),
            ],
            rubric=["Uses service state evidence."],
            failure_modes_tested=["record mutation"],
            difficulty="core",
        )
        issues = validate_workflow(
            workflow,
            surface_map=generate_workflows(request_payload()).surface_map,
            service_map=ServiceMap(services=[service]),
            declared_secrets=[],
            live_service_approval=False,
        )
        self.assertIn("record_mode_mutation", {issue.code for issue in issues})

    def test_mcp_server_url_discovers_tools(self) -> None:
        with patch(
            "gauntlet.workflows.generate.fetch_mcp_tools",
            return_value=[
                {
                    "name": "create_session",
                    "description": "Create browser session",
                    "inputSchema": {"properties": {"url": {"type": "string"}}},
                }
            ],
        ):
            payload = request_payload()
            payload["mcp_server_url"] = "https://mcp.example.test"
            payload["mcp_tools"] = []
            response = generate_workflows(payload)

        self.assertIn("mcp", response.surface_map.interfaces)
        self.assertTrue(any(cap.source == "mcp" for cap in response.surface_map.capabilities))

    def test_api_endpoint_returns_generation_artifact(self) -> None:
        client = TestClient(app)
        response = client.post("/workflows/generate", json=request_payload())

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("surface_map", body)
        self.assertIn("service_map", body)
        self.assertIn("coverage_report", body)
        self.assertIn("capability_graph", body)
        self.assertIn("workflows", body)
        self.assertTrue(body["workflows"])
        self.assertTrue(body["capability_graph"])
        self.assertTrue(body["coverage_report"]["covered_services"])
        self.assertEqual(body["workflows"][0]["execution_harness"], "gauntlet-native")

    def test_api_rejects_malformed_and_empty_requests(self) -> None:
        client = TestClient(app)

        malformed = client.post("/workflows/generate", json={"docs": [{"title": "bad"}]})
        self.assertEqual(malformed.status_code, 422)

        empty = client.post("/workflows/generate", json={})
        self.assertEqual(empty.status_code, 400)
        self.assertIn("provide docs", empty.json()["detail"])

        with patch.dict(os.environ, {"GAUNTLET_PLANNER_API_KEY": "", "OPENAI_API_KEY": ""}, clear=False):
            llm_without_key = client.post("/workflows/generate", json={**request_payload(), "planner": "llm"})
        self.assertEqual(llm_without_key.status_code, 400)
        self.assertIn("PLANNER_API_KEY", llm_without_key.json()["detail"])

    def test_generated_workflows_do_not_reference_undeclared_live_egress(self) -> None:
        response = generate_workflows(request_payload())
        for workflow in response.workflows:
            for rule in workflow.egress_policy:
                self.assertEqual(rule.mode, "twin")
                self.assertTrue(rule.domain.endswith(".local"))

    def test_steel_docs_generate_specific_product_workflows_without_llm(self) -> None:
        response = generate_workflows(
            {
                "docs": [{"title": "steel-llms-full.txt", "text": STEEL_DOCS}],
                "declared_secrets": ["STEEL_API_KEY"],
                "coverage": {"count": 5},
                "planner": "rules",
            }
        )
        names = [workflow.name for workflow in response.workflows]
        self.assertIn("Create, use, and release a Steel browser session with Playwright", names)
        self.assertIn("Compare Steel direct scrape paths across CLI and API", names)
        self.assertIn("Verify Steel profile reuse and authenticated browser context", names)
        self.assertIn("Move a file through a Steel browser session", names)
        self.assertIn("Fetch and summarize a Steel agent trace after a browser run", names)
        self.assertNotIn("Verify Use Steel to launch cloud browsers, scrape content, and automate web tasks", names)
        self.assertEqual(response.coverage_report.covered_surface_areas, ["Agent Traces", "Browser Tools", "Files API", "Profiles API", "Sessions API"])
        self.assertEqual(response.coverage_report.covered_interfaces, ["browser", "cli", "rest", "sdk:python"])

    def test_llm_planner_accepts_specific_high_quality_candidate(self) -> None:
        payload = request_payload()
        docs = parse_docs(payload["docs"])
        surface_map = build_surface_map(docs, parse_repo(payload["repo"]), [], payload["declared_secrets"])
        service_map = build_service_map(payload["services"])
        session_cap = surface_map.capabilities[0].name

        def sender(_: str) -> str:
            return json.dumps({
                "workflows": [
                    {
                        "name": "Run browser session and verify support refund state",
                        "description": "Exercises a realistic Steel-style browser workflow across support service twins.",
                        "audience": "agent_builder",
                        "workflow_type": "agent_under_test",
                        "surface_area": surface_map.capabilities[0].surface_area,
                        "product_capabilities": [session_cap],
                        "services": ["gmail", "stripe", "slack"],
                        "task_prompt": "Using the Python SDK path, create a browser session, inspect the seeded Gmail refund request, look up the matching Stripe payment, draft the customer reply, post a Slack summary, capture the observable result, and release the session.",
                        "required_secrets": ["SUPPORT_API_KEY"],
                        "egress_policy": [
                            {"domain": "gmail.local", "mode": "twin", "service": "gmail"},
                            {"domain": "stripe.local", "mode": "twin", "service": "stripe"},
                            {"domain": "slack.local", "mode": "twin", "service": "slack"},
                        ],
                        "seed_data": [
                            {"service": "gmail", "ref": "gmail.thread:refund-request-001"},
                            {"service": "stripe", "ref": "stripe.payment:pay_1001"},
                            {"service": "slack", "ref": "slack.channel:support"},
                        ],
                        "expected_state_transitions": [
                            "A Gmail draft reply exists for the seeded thread.",
                            "A Slack support-channel summary exists.",
                        ],
                        "success_conditions": [
                            {"description": "The execution trace shows the Python SDK path was used.", "evidence": "transcript"},
                            {"description": "The Gmail twin contains a draft reply for the seeded thread.", "evidence": "twin_state"},
                            {"description": "The Slack twin contains a summary referencing the payment status.", "evidence": "twin_state"},
                            {"description": "The final answer cites the observed records and session cleanup.", "evidence": "artifact"},
                        ],
                        "rubric": [
                            "The agent completed the task end-to-end instead of describing a plan.",
                            "The agent used seed data or service responses for every identifier.",
                            "The agent used only declared twin routes.",
                        ],
                        "failure_modes_tested": ["multi-service state chaining", "false success", "cleanup verification"],
                        "difficulty": "hard",
                        "selection_reason": "Covers browser automation plus service-twin state verification.",
                    }
                ]
            })

        planner = LLMPlanner(sender=sender)
        workflows = planner.generate_candidates(
            parse_request(payload),
            surface_map,
            service_map,
        )
        self.assertEqual(len(workflows), 1)
        self.assertEqual(len(workflows[0].services), 3)
        response = generate_workflows({**payload, "planner": "rules"})
        self.assertTrue(response.coverage_report.harness_results)

    def test_llm_planner_uses_gemini_when_gemini_key_is_configured(self) -> None:
        calls = {"gemini": 0}

        def fake_gemini(prompt: str) -> str:
            calls["gemini"] += 1
            self.assertIn("Gauntlet", prompt)
            return '{"workflows":[]}'

        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key", "GAUNTLET_PLANNER_PROVIDER": "gemini"}, clear=False):
            with patch.object(llm_planner, "_send_gemini_prompt", side_effect=fake_gemini):
                planner = LLMPlanner()
                self.assertTrue(planner.available())
                docs = parse_docs(request_payload()["docs"])
                surface_map = build_surface_map(docs, parse_repo(request_payload()["repo"]), [], request_payload()["declared_secrets"])
                service_map = build_service_map(request_payload()["services"])
                workflows = planner.generate_candidates(parse_request(request_payload()), surface_map, service_map)

        self.assertEqual(workflows, [])
        self.assertEqual(calls["gemini"], 1)

    def test_llm_repair_turns_invalid_candidate_into_valid_workflow(self) -> None:
        payload = request_payload()
        docs = parse_docs(payload["docs"])
        surface_map = build_surface_map(docs, parse_repo(payload["repo"]), [], payload["declared_secrets"])
        service_map = build_service_map(payload["services"])
        cap = surface_map.capabilities[0].name
        calls = {"count": 0}

        def sender(_: str) -> str:
            calls["count"] += 1
            if calls["count"] == 1:
                return '{"workflows":[{"name":"Bad fake workflow","description":"bad","audience":"agent_builder","workflow_type":"agent_under_test","surface_area":"x","product_capabilities":["not real"],"services":["gmail"],"task_prompt":"Use fake_id_123 correctly.","success_conditions":[{"description":"It works correctly.","evidence":"transcript"}],"rubric":[],"failure_modes_tested":[],"difficulty":"core"}]}'
            return json.dumps({
                "workflows": [
                    {
                        "name": "Repair Gmail refund workflow",
                        "description": "Uses declared seed data and twin state to verify support automation.",
                        "audience": "agent_builder",
                        "workflow_type": "agent_under_test",
                        "surface_area": surface_map.capabilities[0].surface_area,
                        "product_capabilities": [cap],
                        "services": ["gmail"],
                        "task_prompt": "Using the documented API path, read the seeded Gmail refund request, create a draft reply from observed thread data, verify the draft exists in the Gmail twin, and report the evidence.",
                        "required_secrets": ["SUPPORT_API_KEY"],
                        "egress_policy": [{"domain": "gmail.local", "mode": "twin", "service": "gmail"}],
                        "seed_data": [{"service": "gmail", "ref": "gmail.thread:refund-request-001"}],
                        "expected_state_transitions": ["The Gmail twin contains a draft reply for the seeded thread."],
                        "success_conditions": [
                            {"description": "The seeded Gmail thread was read before drafting.", "evidence": "transcript"},
                            {"description": "The Gmail twin contains the draft reply.", "evidence": "twin_state"},
                            {"description": "The final answer cites the observed thread and draft evidence.", "evidence": "artifact"},
                        ],
                        "rubric": [
                            "The agent completed the draft workflow end-to-end.",
                            "The agent did not invent identifiers.",
                            "The agent verified Gmail twin state.",
                        ],
                        "failure_modes_tested": ["identifier grounding", "false success", "side-effect verification"],
                        "difficulty": "core",
                    }
                ]
            })

        planner = LLMPlanner(sender=sender)
        request = parse_request(payload)
        bad = planner.generate_candidates(request, surface_map, service_map)[0]
        repaired = planner.repair_candidate(bad, ["unknown_capability", "placeholder_data"], request, surface_map, service_map)
        self.assertIsNotNone(repaired)
        self.assertEqual(repaired.services[0].name, "gmail")


if __name__ == "__main__":
    unittest.main()
