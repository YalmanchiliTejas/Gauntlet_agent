"""Tests for the boundary between generated user requests and hidden harness oracles."""
import unittest

from gauntlet.workflows.quality import normalize_workflow_quality
from gauntlet.workflows.schema import WorkflowDraft


class AgentVisibleWorkflowTests(unittest.TestCase):
    def test_agent_input_excludes_hidden_harness_contract(self) -> None:
        workflow = WorkflowDraft(
            name="Investigate payment issue",
            description="Investigate a payment issue and prepare a customer response.",
            audience="agent_builder",
            workflow_type="agent_under_test",
            surface_area="support",
            product_capabilities=["lookup payment"],
            services=[],
            task_prompt="INTERNAL: use Stripe lookup, create a Gmail draft, assert draft state, then record cleanup.",
            required_secrets=[],
            egress_policy=[],
            seed_data=[],
            expected_state_transitions=["Draft exists in the Gmail twin."],
            success_conditions=[],
            rubric=["Uses the seeded payment id."],
            failure_modes_tested=["wrong identifier"],
            difficulty="core",
            test_fixtures={"payment_id": "pay_seed_001"},
            user_prompt="A customer says they were charged but their order failed. Please investigate the payment and prepare a response for them.",
        )

        payload = workflow.agent_input()

        self.assertEqual(payload["user_prompt"], workflow.user_prompt)
        self.assertNotIn("task_prompt", payload)
        self.assertNotIn("rubric", payload)
        self.assertNotIn("test_fixtures", payload)
        self.assertNotIn("success_conditions", payload)

    def test_legacy_rule_candidate_gets_user_prompt_without_exposing_brief(self) -> None:
        workflow = WorkflowDraft(
            name="Retrieve account summary",
            description="Retrieve an account summary and explain the result to the customer.",
            audience="agent_builder",
            workflow_type="agent_under_test",
            surface_area="accounts",
            product_capabilities=["retrieve account"],
            services=[],
            task_prompt="INTERNAL: call the REST endpoint, assert status 200 and response.account_id, then save the API response artifact.",
            required_secrets=[],
            egress_policy=[],
            seed_data=[],
            expected_state_transitions=[],
            success_conditions=[],
            rubric=[],
            failure_modes_tested=["wrong interface"],
            difficulty="core",
        )

        normalize_workflow_quality(workflow)

        self.assertTrue(workflow.user_prompt.startswith("Please help me with this request."))
        self.assertNotIn("REST endpoint", workflow.agent_input()["user_prompt"])


if __name__ == "__main__":
    unittest.main()
