from __future__ import annotations

import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from gauntlet.app import app
from gauntlet.workflows.generate import generate_workflows, parse_request
from gauntlet.workflows import llm_planner
from gauntlet.workflows.harness import GauntletNativeDryRunScorer
from gauntlet.workflows.llm_planner import LLMPlanner
from gauntlet.workflows.probe import build_surface_map, parse_docs, parse_repo
from gauntlet.workflows.service_map import build_service_map
from gauntlet.workflows.schema import (
    Capability,
    EgressRule,
    ProductSurfaceMap,
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


BROWSER_AUTOMATION_DOCS = """
# Cloud Browser Product Documentation
Cloud Browser is an API for agents and developers.
Use Cloud Browser to launch hosted browser sessions, scrape content, and automate web tasks.

## Quick Reference
- Install: `npm install cloud-browser-sdk` or `pip install cloud-browser-sdk`
- CLI: `browserctl scrape https://example.com`
- Auth env var: `PRODUCT_API_KEY`
- API base URL: `https://api.example-browser.test`

## Agent Instructions
For browser automation, connect Puppeteer or Playwright via WebSocket.
Use `client.sessions.create()`, connect Playwright over CDP, navigate to a page, close the browser, and release the session.
For simple scraping without a browser session, use the REST scrape endpoint `/v1/scrape` or `client.scrape()`.

## Profiles API
Reuse browser context, auth, cookies, extensions, credentials, and browser settings across sessions.

## Files API
Upload, download, manage and work with files within an active session.

## Agent Traces
Fetch the activity timeline for a browser session as JSON and summarize trace events.
"""


PAYMENTS_DOCS = """
# LedgerPay API
LedgerPay lets support agents inspect invoices, create refunds, and review audit events.

## API Reference
- Auth env var: `LEDGERPAY_API_KEY`
- API base URL: `https://api.ledgerpay.test`
- Create a refund for an invoice after reading invoice status.
- Get invoice details by invoice id.
- Upload refund evidence files to the refund record.
- List audit events for a refund and cite event timestamps.
- Delete a draft refund when verification fails.
"""


ISSUE_TRACKER_DOCS = """
# TaskTrack CLI
TaskTrack is an issue tracker for engineering teams.

## Commands
- Auth env var: `TASKTRACK_TOKEN`
- API base URL: `https://api.tasktrack.test`
- CLI: `tasktrack issue create --title <title>`
- CLI: `tasktrack issue get --id <issue_id>`
- Update ticket status and add a comment.
- Search issues by label and assignee.
- Export issue history events as JSON.
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

    def test_browser_docs_generate_generic_product_workflows_without_llm(self) -> None:
        response = generate_workflows(
            {
                "docs": [{"title": "browser-product-docs.md", "text": BROWSER_AUTOMATION_DOCS}],
                "declared_secrets": ["PRODUCT_API_KEY"],
                "coverage": {"count": 5},
                "planner": "rules",
            }
        )
        names = [workflow.name for workflow in response.workflows]
        joined_names = " ".join(names).lower()
        self.assertIn("clean up", joined_names)
        self.assertTrue("retrieve" in joined_names or "scrape" in joined_names)
        self.assertIn("artifact", joined_names)
        self.assertIn("observability", joined_names)
        self.assertIn("primary_api", response.coverage_report.covered_services)
        self.assertIn("api.example-browser.test", [service.domain for service in response.service_map.services])
        self.assertIn("Agent Traces", response.coverage_report.covered_surface_areas)
        self.assertIn("Files API", response.coverage_report.covered_surface_areas)
        self.assertEqual(response.coverage_report.covered_interfaces, ["browser", "cli", "rest", "sdk:python"])

    def test_docs_and_count_only_are_enough_for_user_facing_generation(self) -> None:
        with patch.dict(os.environ, {"GEMINI_API_KEY": "", "GAUNTLET_PLANNER_API_KEY": "", "OPENAI_API_KEY": ""}, clear=False):
            response = generate_workflows(
                {
                    "docs": [{"title": "browser-product-docs.md", "text": BROWSER_AUTOMATION_DOCS}],
                    "coverage": {"count": 3},
                }
            )

        self.assertEqual(len(response.workflows), 3)
        self.assertTrue(response.coverage_report.covered_surface_areas)
        self.assertTrue(all(len(workflow.rubric) >= 3 for workflow in response.workflows))

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
                        "description": "Exercises a realistic product-style browser workflow across support service twins.",
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

    def test_llm_mode_combines_rule_candidates_and_expands_thin_rubrics(self) -> None:
        payload = {
            "docs": [{"title": "browser-product-docs.md", "text": BROWSER_AUTOMATION_DOCS}],
            "declared_secrets": ["PRODUCT_API_KEY"],
            "coverage": {"count": 5},
            "planner": "llm",
            "combine_rule_candidates": True,
            "repair_attempts": 0,
        }

        def fake_send(prompt: str) -> str:
            self.assertIn("Generate", prompt)
            return json.dumps(
                {
                    "workflows": [
                        {
                            "name": "Thin rubric JS session workflow",
                            "description": "Creates a browser session with JavaScript and captures browser evidence.",
                            "audience": "agent_builder",
                            "workflow_type": "agent_under_test",
                            "surface_area": "JavaScript SDK",
                            "product_capabilities": ["Use Cloud Browser to launch hosted browser sessions, scrape content, and automate web tasks"],
                            "target_interfaces": ["sdk:javascript", "browser"],
                            "services": ["primary_api"],
                            "task_prompt": "Using the JavaScript SDK and Puppeteer, create a Cloud Browser browser session, connect to it, navigate to https://example.com, capture a screenshot artifact, release the session, and report the evidence.",
                            "required_secrets": ["PRODUCT_API_KEY"],
                            "egress_policy": [{"domain": "api.example-browser.test", "mode": "twin", "service": "primary_api"}],
                            "seed_data": [],
                            "test_fixtures": {
                                "target_url": "https://example.com",
                                "expected_title_contains": "Example Domain",
                                "create_operations": ["client.sessions.create()"],
                                "use_operations": ["chromium.connectOverCDP()", "page.goto('https://example.com')"],
                                "cleanup_operations": ["client.sessions.release(session.id)"],
                            },
                            "expected_artifacts": ["session_id", "screenshot", "release_response"],
                            "expected_state_transitions": ["A browser session is created, used, released, and post-release state shows it is no longer active."],
                            "success_conditions": [
                                {"description": "The session creation API returned an id.", "evidence": "api_response"},
                                {"description": "A screenshot artifact from https://example.com was captured.", "evidence": "artifact"},
                                {"description": "The release response or post-release lookup proves the created session id is no longer active.", "evidence": "api_response"},
                            ],
                            "rubric": ["The workflow creates, uses, and releases a browser session."],
                            "failure_modes_tested": ["session lifecycle", "artifact verification", "cleanup verification"],
                            "difficulty": "hard",
                            "cleanup_required": True,
                        }
                    ]
                }
            )

        with patch.object(llm_planner, "_send_prompt", side_effect=fake_send):
            response = generate_workflows(payload)

        names = [workflow.name for workflow in response.workflows]
        self.assertIn("Thin rubric JS session workflow", names)
        self.assertTrue(
            any(
                "documented" in name.lower()
                or "retrieve" in name.lower()
                or "observability" in name.lower()
                for name in names
            )
        )
        thin = next(workflow for workflow in response.workflows if workflow.name == "Thin rubric JS session workflow")
        self.assertGreaterEqual(len(thin.rubric), 3)

    def test_llm_unknown_refs_remain_visible_for_validation(self) -> None:
        payload = {
            "docs": [{"title": "browser-product-docs.md", "text": BROWSER_AUTOMATION_DOCS}],
            "declared_secrets": ["PRODUCT_API_KEY"],
            "coverage": {"count": 3},
            "planner": "llm",
            "combine_rule_candidates": False,
            "repair_attempts": 0,
        }

        def fake_send(_: str) -> str:
            return json.dumps(
                {
                    "workflows": [
                        {
                            "name": "Hallucinated service workflow",
                            "description": "Should be rejected instead of silently sanitized.",
                            "audience": "agent_builder",
                            "workflow_type": "agent_under_test",
                            "surface_area": "Unknown",
                            "product_capabilities": ["made up capability"],
                            "target_interfaces": ["rest"],
                            "services": ["notion"],
                            "task_prompt": "Using the REST API, create a fake record through a hallucinated service and verify it with a concrete response artifact.",
                            "required_secrets": ["PRODUCT_API_KEY"],
                            "egress_policy": [{"domain": "api.example-browser.test", "mode": "twin", "service": "primary_api"}],
                            "seed_data": [],
                            "expected_state_transitions": ["A fake record is created."],
                            "success_conditions": [
                                {"description": "The API response contains status 200.", "evidence": "api_response"},
                                {"description": "The transcript names the REST call.", "evidence": "transcript"},
                                {"description": "The artifact contains the returned id.", "evidence": "artifact"},
                            ],
                            "rubric": ["Uses real docs.", "Uses declared routes.", "Verifies concrete evidence."],
                            "failure_modes_tested": ["hallucinated integration"],
                            "difficulty": "core",
                        }
                    ]
                }
            )

        with patch.object(llm_planner, "_send_prompt", side_effect=fake_send):
            response = generate_workflows(payload)

        self.assertFalse(response.workflows)
        rejected_codes = {issue.code for item in response.coverage_report.rejected_candidates for issue in item.reasons}
        self.assertIn("unknown_service", rejected_codes)
        self.assertIn("unknown_capability", rejected_codes)

    def test_docs_domains_are_not_implicitly_approved_as_egress(self) -> None:
        request = parse_request(
            {
                "docs": [{"title": "docs.md", "text": "Call https://api.example.com with EXAMPLE_API_KEY."}],
                "declared_secrets": ["EXAMPLE_API_KEY"],
            }
        )

        self.assertEqual(request.egress_domains, [])

    def test_browser_workflows_have_routes_fixtures_and_oracles(self) -> None:
        response = generate_workflows(
            {
                "docs": [{"title": "browser-product-docs.md", "text": BROWSER_AUTOMATION_DOCS}],
                "declared_secrets": ["PRODUCT_API_KEY"],
                "coverage": {"count": 5},
                "planner": "rules",
            }
        )

        self.assertIn("primary_api", response.coverage_report.covered_services)
        for workflow in response.workflows:
            self.assertTrue(workflow.test_fixtures)
            self.assertTrue(workflow.expected_artifacts)
            self.assertTrue(workflow.run_readiness)
            self.assertTrue(any(rule.domain == "api.example-browser.test" and rule.mode == "twin" for rule in workflow.egress_policy))
            if workflow.cleanup_required:
                cleanup_text = " ".join(
                    [workflow.task_prompt]
                    + workflow.expected_state_transitions
                    + [condition.description for condition in workflow.success_conditions]
                ).lower()
                self.assertTrue(
                    "post-release" in cleanup_text
                    or "post-cleanup" in cleanup_text
                    or "no longer active" in cleanup_text
                    or "release response" in cleanup_text
                    or "cleanup response" in cleanup_text
                )

    def test_rules_prompts_include_concrete_documented_operations(self) -> None:
        response = generate_workflows(
            {
                "docs": [{"title": "browser-product-docs.md", "text": BROWSER_AUTOMATION_DOCS}],
                "declared_secrets": ["PRODUCT_API_KEY"],
                "coverage": {"count": 5},
                "planner": "rules",
            }
        )
        prompts = "\n".join(workflow.task_prompt for workflow in response.workflows)

        self.assertTrue(
            "client.sessions.create()" in prompts
            or "sessions.create()" in prompts
        )
        self.assertTrue(
            "/v1/scrape" in prompts
            or "client.scrape()" in prompts
            or "browserctl scrape" in prompts
        )
        self.assertNotIn("Using a documented rest, browser interface", prompts)
        lifecycle = next(workflow for workflow in response.workflows if workflow.name.startswith("Create, use, and clean up"))
        self.assertNotIn("client.sessions.create()", lifecycle.test_fixtures.get("cleanup_operations", []))
        self.assertTrue(any("release" in operation.lower() or "close" in operation.lower() for operation in lifecycle.test_fixtures.get("cleanup_operations", [])))

    def test_workflow_generator_has_no_product_specific_runtime_strings(self) -> None:
        root = Path(__file__).resolve().parents[1]
        scanned = []
        for path in (root / "gauntlet" / "workflows").glob("*.py"):
            scanned.append(path.read_text())
        scanned.append((root / "scripts" / "generate_workflows.py").read_text())
        joined = "\n".join(scanned).lower()

        forbidden_terms = (
            "st" + "eel",
            "st" + "eel_api",
            "api." + "st" + "eel.dev",
        )
        for forbidden in forbidden_terms:
            self.assertNotIn(forbidden, joined)

    def test_generic_first_party_api_inference_from_any_base_url(self) -> None:
        response = generate_workflows(
            {
                "docs": [{"title": "payments.md", "text": PAYMENTS_DOCS}],
                "declared_secrets": ["LEDGERPAY_API_KEY"],
                "coverage": {"count": 4},
                "planner": "rules",
            }
        )

        self.assertEqual(response.service_map.services[0].name, "primary_api")
        self.assertEqual(response.service_map.services[0].domain, "api.ledgerpay.test")
        self.assertIn("primary_api", response.coverage_report.covered_services)
        self.assertTrue(all(workflow.test_fixtures for workflow in response.workflows))
        self.assertTrue(all(workflow.expected_artifacts for workflow in response.workflows))

    def test_non_browser_product_docs_generate_quality_workflows(self) -> None:
        for title, docs, secret, domain in [
            ("payments.md", PAYMENTS_DOCS, "LEDGERPAY_API_KEY", "api.ledgerpay.test"),
            ("issues.md", ISSUE_TRACKER_DOCS, "TASKTRACK_TOKEN", "api.tasktrack.test"),
        ]:
            response = generate_workflows(
                {
                    "docs": [{"title": title, "text": docs}],
                    "declared_secrets": [secret],
                    "coverage": {"count": 4},
                    "planner": "rules",
                }
            )
            self.assertGreaterEqual(len(response.workflows), 3)
            self.assertIn(domain, [service.domain for service in response.service_map.services])
            self.assertTrue(response.coverage_report.coverage_matrix)
            self.assertTrue(any("artifact" in workflow.quality_badges or workflow.expected_artifacts for workflow in response.workflows))
            self.assertTrue(any("false success" in " ".join(workflow.failure_modes_tested).lower() for workflow in response.workflows))

    def test_coverage_report_has_matrix_and_suite_context(self) -> None:
        response = generate_workflows(request_payload())

        self.assertTrue(response.coverage_report.suite_narrative)
        self.assertTrue(response.coverage_report.coverage_matrix)
        self.assertTrue(response.coverage_report.catches)
        self.assertIsInstance(response.coverage_report.gaps, list)

    def test_harness_blocks_missing_concrete_operations(self) -> None:
        workflow = WorkflowDraft(
            name="Generic API lifecycle",
            description="Looks concrete but has no documented operation binding.",
            audience="agent_builder",
            workflow_type="agent_under_test",
            surface_area="REST API",
            product_capabilities=["Create and verify records"],
            services=[ServiceDependency(name="primary_api", mode="twin", domain="api.product.test")],
            task_prompt="Using the REST API, create a record, verify the response artifact, clean up the record, and report the observed status.",
            required_secrets=["PRODUCT_API_KEY"],
            egress_policy=[EgressRule(domain="api.product.test", mode="twin", service="primary_api")],
            seed_data=[],
            expected_state_transitions=["A record is created and then cleaned up."],
            success_conditions=[
                SuccessCondition("The API response contains status 201.", "api_response"),
                SuccessCondition("The created record id appears in the artifact.", "artifact"),
                SuccessCondition("The post-cleanup lookup returns status 404.", "api_response"),
            ],
            rubric=["Creates state.", "Verifies state.", "Cleans up state."],
            failure_modes_tested=["false success"],
            difficulty="core",
            cleanup_required=True,
            target_interfaces=["rest"],
            test_fixtures={"record_name": "gauntlet-test-record"},
            expected_artifacts=["created_record_id", "post_cleanup_status"],
        )

        result = GauntletNativeDryRunScorer().score(
            workflow,
            ProductSurfaceMap(
                interfaces=["rest"],
                capabilities=[Capability(name="Create and verify records", surface_area="REST API", interfaces=["rest"])],
            ),
            ServiceMap(services=workflow.services),
        )

        self.assertFalse(result.feasible)
        self.assertFalse(result.readiness["ready"])
        self.assertIn("missing_concrete_operation", {defect.code for defect in result.defects})

    def test_harness_detects_incompatible_operation_chains(self) -> None:
        workflow = WorkflowDraft(
            name="Mixed resource lifecycle",
            description="Creates unrelated resources in one lifecycle workflow.",
            audience="agent_builder",
            workflow_type="agent_under_test",
            surface_area="REST API",
            product_capabilities=["Manage CRM records"],
            services=[],
            task_prompt="Using the REST API, create a contact and a deal, verify their responses, then delete the contact and report cleanup evidence.",
            required_secrets=[],
            egress_policy=[],
            seed_data=[],
            expected_state_transitions=["A contact and deal are created, then the contact is deleted."],
            success_conditions=[
                SuccessCondition("POST /v1/contacts returns status 201.", "api_response"),
                SuccessCondition("POST /v1/deals returns status 201.", "api_response"),
                SuccessCondition("DELETE /v1/contacts/{contact_id} returns status 204.", "api_response"),
            ],
            rubric=["Uses documented endpoints.", "Does not mix identifiers.", "Verifies cleanup."],
            failure_modes_tested=["resource mismatch"],
            difficulty="hard",
            cleanup_required=True,
            target_interfaces=["rest"],
            test_fixtures={
                "create_operations": ["POST /v1/contacts", "POST /v1/deals"],
                "cleanup_operations": ["DELETE /v1/contacts/{contact_id}"],
                "contact_email": "gauntlet-contact@example.test",
            },
            expected_artifacts=["contact_id", "deal_id", "cleanup_status"],
        )

        result = GauntletNativeDryRunScorer().score(workflow, ProductSurfaceMap(interfaces=["rest"]), ServiceMap())

        self.assertFalse(result.feasible)
        self.assertIn("operation_chain_incompatible", {defect.code for defect in result.defects})

    def test_harness_blocks_unsafe_side_effect_without_seed_or_policy(self) -> None:
        workflow = WorkflowDraft(
            name="Send campaign",
            description="Sends a campaign without grounding.",
            audience="agent_builder",
            workflow_type="agent_under_test",
            surface_area="Marketing API",
            product_capabilities=["Send campaigns"],
            services=[ServiceDependency(name="primary_api", mode="twin", domain="api.product.test")],
            task_prompt="Using the REST API, send campaign camp_123, verify the send response, and report the delivery event id.",
            required_secrets=["PRODUCT_API_KEY"],
            egress_policy=[EgressRule(domain="api.product.test", mode="twin", service="primary_api")],
            seed_data=[],
            expected_state_transitions=["A campaign send is triggered."],
            success_conditions=[
                SuccessCondition("POST /v1/campaigns/{campaign_id}/send returns status 202.", "api_response"),
                SuccessCondition("The response contains event id send_evt_001.", "api_response"),
                SuccessCondition("The delivery state contains campaign_id camp_123.", "twin_state"),
            ],
            rubric=["Uses the REST API.", "Verifies the send response.", "Reports evidence."],
            failure_modes_tested=["unsafe side effect"],
            difficulty="hard",
            target_interfaces=["rest"],
            test_fixtures={"operation": "POST /v1/campaigns/{campaign_id}/send", "campaign_id": "camp_123"},
            expected_artifacts=["send_evt_001"],
        )

        result = GauntletNativeDryRunScorer().score(workflow, ProductSurfaceMap(interfaces=["rest"]), ServiceMap(services=workflow.services))

        self.assertFalse(result.feasible)
        self.assertEqual(result.risk_level, "high")
        self.assertIn("unsafe_side_effect_without_seed", {defect.code for defect in result.defects})

    def test_harness_requires_specific_machine_checkable_oracles(self) -> None:
        workflow = WorkflowDraft(
            name="Vague artifact workflow",
            description="Has an operation but no checkable oracle.",
            audience="agent_builder",
            workflow_type="agent_under_test",
            surface_area="Files API",
            product_capabilities=["Upload files"],
            services=[],
            task_prompt="Using the REST API, upload a small file through the documented endpoint, retrieve it, and summarize whether the workflow behaved as expected.",
            required_secrets=[],
            egress_policy=[],
            seed_data=[],
            expected_state_transitions=["A file is uploaded and retrieved."],
            success_conditions=[
                SuccessCondition("The upload works as expected.", "api_response"),
                SuccessCondition("The file is handled correctly.", "artifact"),
                SuccessCondition("The final answer is appropriate.", "transcript"),
            ],
            rubric=["Uploads a file.", "Retrieves a file.", "Summarizes the result."],
            failure_modes_tested=["weak oracle"],
            difficulty="core",
            target_interfaces=["rest"],
            test_fixtures={"operation": "POST /v1/files", "filename": "gauntlet-note.txt"},
            expected_artifacts=["file_artifact"],
        )

        result = GauntletNativeDryRunScorer().score(workflow, ProductSurfaceMap(interfaces=["rest"]), ServiceMap())

        self.assertFalse(result.feasible)
        self.assertIn("weak_oracle", {defect.code for defect in result.defects})

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
