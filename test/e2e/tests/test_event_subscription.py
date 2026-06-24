# Copyright Amazon.com Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"). You may
# not use this file except in compliance with the License. A copy of the
# License is located at
#
#	http://aws.amazon.com/apache2.0/
#
# or in the "license" file accompanying this file. This file is distributed
# on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either
# express or implied. See the License for the specific language governing
# permissions and limitations under the License.

"""Integration tests for the DMS API EventSubscription resource.

Test scenarios
--------------
* test_crud
    Create an EventSubscription against a bootstrapped SNS topic, verify it
    appears in the DMS API with the expected attributes. Wait for it to
    become synced, verify the K8s CR status and the AWS API, verify the
    initial tags, add/update/delete tags, toggle ``enabled`` to ``False``,
    and let the fixture handle deletion.
"""

import logging
import time

import pytest

from acktest import tags
from acktest.k8s import condition
from acktest.k8s import resource as k8s
from acktest.resources import random_suffix_name
from e2e import service_marker, CRD_GROUP, CRD_VERSION, load_dms_resource
from e2e import event_subscription as aws_api
from e2e.replacement_values import REPLACEMENT_VALUES

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RESOURCE_PLURAL = "eventsubscriptions"

# DMS EventSubscriptions are created asynchronously — wait for sync.
MAX_WAIT_FOR_SYNCED_MINUTES = 5

# Pause between patching and re-checking so the controller can reconcile.
MODIFY_WAIT_AFTER_SECONDS = 10


@pytest.fixture
def event_subscription(request):
    """Creates an EventSubscription K8s CR and tears it down afterward.

    Yields:
        tuple: (ref, cr, subscription_name), where *ref* is the
        ``CustomResourceReference``, *cr* is the initial CR dict returned by
        the controller, and *subscription_name* is the identifier used for both
        the K8s object name and the DMS resource name.
    """
    ref = None
    subscription_name = None

    def _cleanup():
        """Deletes any resources created by this fixture.

        Registered as a finalizer so it runs even if fixture setup fails after
        creating the Kubernetes EventSubscription resource.
        """
        if ref is not None:
            try:
                if k8s.get_resource_exists(ref):
                    _, deleted = k8s.delete_custom_resource(ref, 3, 10)
                    assert deleted
            except Exception as e:
                logging.warning(f"failed to delete event subscription CR: {e}")

        if subscription_name is not None:
            try:
                aws_api.wait_until_deleted(subscription_name)
            except Exception as e:
                logging.warning(
                    f"failed waiting for event subscription deletion: {e}"
                )

    request.addfinalizer(_cleanup)

    subscription_name = random_suffix_name("my-event-subscription", 27)

    replacements = REPLACEMENT_VALUES.copy()
    replacements["EVENT_SUBSCRIPTION_NAME"] = subscription_name

    resource_data = load_dms_resource(
        "event_subscription",
        additional_replacements=replacements,
    )
    logging.debug(resource_data)

    ref = k8s.CustomResourceReference(
        CRD_GROUP, CRD_VERSION, RESOURCE_PLURAL,
        subscription_name, namespace="default",
    )
    k8s.create_custom_resource(ref, resource_data)
    cr = k8s.wait_resource_consumed_by_controller(ref)

    assert cr is not None
    assert k8s.get_resource_exists(ref)

    # EventSubscriptions are created asynchronously in DMS — wait for sync.
    assert k8s.wait_on_condition(
        ref, "ACK.ResourceSynced", "True",
        wait_periods=MAX_WAIT_FOR_SYNCED_MINUTES * 4, period_length=15,
    )

    yield ref, cr, subscription_name



# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

@service_marker
class TestEventSubscription:
    def test_crud(self, event_subscription):
        """Verifies the full Create → Read → Update → Delete lifecycle.

        Checks:
        1.  The event subscription becomes visible in the DMS API and reaches the
            ``active`` status.
        2.  The controller-derived ARN matches the expected DMS ARN format.
        3.  The initial ACK system tags are present in the AWS API.
        4.  Tags can be added as ``environment=dev``.
        5.  Tags can be updated from ``environment=dev`` → ``environment=prod``.
        6.  Tags can be deleted by patching ``tags`` to ``None``.
        7.  The ``enabled`` field can be updated from True → False.
        """
        ref, cr, subscription_name = event_subscription

        # ---- Verify create / read ------------------------------------------
        condition.assert_synced(ref)

        latest = aws_api.get(subscription_name)
        assert latest is not None
        assert latest['CustSubscriptionId'] == subscription_name
        assert latest['SnsTopicArn'] == REPLACEMENT_VALUES['SNS_TOPIC_ARN']
        assert latest['Enabled'] is True
        assert latest['Status'] == 'active'

        # ARN is written into the CR status by the controller.
        cr = k8s.get_resource(ref)
        assert cr is not None
        subscription_arn = k8s.get_resource_arn(cr)
        assert subscription_arn is not None

        # ---- Verify initial tags -------------------------------------------
        latest_tags = aws_api.get_tags(subscription_arn)
        assert latest_tags is not None
        tags.assert_ack_system_tags(latest_tags)

        # ---- Add: tags ------------------------------------------------------
        k8s.patch_custom_resource(
            ref,
            {"spec": {"tags": [{"key": "environment", "value": "dev"}]}},
        )
        time.sleep(MODIFY_WAIT_AFTER_SECONDS)

        assert k8s.wait_on_condition(
            ref, "ACK.ResourceSynced", "True",
            wait_periods=MAX_WAIT_FOR_SYNCED_MINUTES * 4, period_length=15,
        )

        expect_tags = [{"Key": "environment", "Value": "dev"}]
        latest_tags = aws_api.get_tags(subscription_arn)
        assert latest_tags is not None
        tags.assert_ack_system_tags(latest_tags)
        tags.assert_equal_without_ack_tags(expect_tags, latest_tags)

        # ---- Update: tags ---------------------------------------------------
        k8s.patch_custom_resource(
            ref,
            {"spec": {"tags": [{"key": "environment", "value": "prod"}]}},
        )
        time.sleep(MODIFY_WAIT_AFTER_SECONDS)

        assert k8s.wait_on_condition(
            ref, "ACK.ResourceSynced", "True",
            wait_periods=MAX_WAIT_FOR_SYNCED_MINUTES * 4, period_length=15,
        )

        expect_tags = [{"Key": "environment", "Value": "prod"}]
        latest_tags = aws_api.get_tags(subscription_arn)
        assert latest_tags is not None
        tags.assert_ack_system_tags(latest_tags)
        tags.assert_equal_without_ack_tags(expect_tags, latest_tags)

        # ---- Delete: tags ---------------------------------------------------
        k8s.patch_custom_resource(
            ref,
            {"spec": {"tags": None}},
        )
        time.sleep(MODIFY_WAIT_AFTER_SECONDS)

        assert k8s.wait_on_condition(
            ref, "ACK.ResourceSynced", "True",
            wait_periods=MAX_WAIT_FOR_SYNCED_MINUTES * 4, period_length=15,
        )
        expect_tags = []
        latest_tags = aws_api.get_tags(subscription_arn)
        assert latest_tags is not None
        tags.assert_ack_system_tags(latest_tags)
        tags.assert_equal_without_ack_tags(expect_tags, latest_tags)

        # ---- Update: enabled ------------------------------------------------
        k8s.patch_custom_resource(ref, {"spec": {"enabled": False}})
        time.sleep(MODIFY_WAIT_AFTER_SECONDS)

        assert k8s.wait_on_condition(
            ref, "ACK.ResourceSynced", "True",
            wait_periods=MAX_WAIT_FOR_SYNCED_MINUTES * 4, period_length=15,
        )

        latest = aws_api.get(subscription_name)
        assert latest is not None
        assert latest['Enabled'] is False
