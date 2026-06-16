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

"""Integration tests for the DMS API Endpoint resource.

Test scenarios
--------------
* test_crud
    Create an S3 target Endpoint against a bootstrapped S3 bucket and IAM
    role, wait for it to become *active*, verify the K8s CR status and the
    AWS API, verify initial ACK system tags, add an ``environment=dev`` tag,
    update it to ``environment=prod``, delete all tags, update the
    ``s3Settings.bucketFolder`` field, verify the change is reflected in the
    AWS API, and let the fixture handle deletion.
"""

import logging
import time

import pytest

from acktest import tags
from acktest.k8s import condition
from acktest.k8s import resource as k8s
from acktest.resources import random_suffix_name
from e2e import service_marker, CRD_GROUP, CRD_VERSION, load_dms_resource
from e2e import endpoint as aws_api
from e2e.replacement_values import REPLACEMENT_VALUES

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RESOURCE_PLURAL = "endpoints"

# DMS S3 target endpoints become active quickly.
MAX_WAIT_FOR_SYNCED_MINUTES = 5

# Pause between patching and re-checking so the controller can reconcile.
MODIFY_WAIT_AFTER_SECONDS = 10

INITIAL_BUCKET_FOLDER = "ack-initial"
UPDATED_BUCKET_FOLDER = "ack-updated"


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def endpoint(request):
    """Creates an S3 target Endpoint CR and tears it down after the test.

    Yields:
        tuple: (ref, cr, endpoint_name)
    """
    ref = None
    endpoint_name = None

    def _cleanup():
        """Deletes any resources created by this fixture.

        Registered as a finalizer so it runs even if fixture setup fails after
        creating the Kubernetes Endpoint resource.
        """
        if ref is not None:
            try:
                if k8s.get_resource_exists(ref):
                    _, deleted = k8s.delete_custom_resource(ref, 3, 10)
                    assert deleted
            except Exception as e:
                logging.warning(f"failed to delete endpoint CR: {e}")

        if endpoint_name is not None:
            try:
                aws_api.wait_until_deleted(endpoint_name)
            except Exception as e:
                logging.warning(f"failed waiting for endpoint deletion: {e}")

    request.addfinalizer(_cleanup)

    endpoint_name = random_suffix_name("my-dms-endpoint", 21)

    replacements = REPLACEMENT_VALUES.copy()
    replacements["ENDPOINT_NAME"] = endpoint_name
    replacements["ENDPOINT_BUCKET_FOLDER"] = INITIAL_BUCKET_FOLDER
    replacements["ENDPOINT_TYPE"] = "target"

    resource_data = load_dms_resource(
        "endpoint",
        additional_replacements=replacements,
    )
    logging.debug(resource_data)

    ref = k8s.CustomResourceReference(
        CRD_GROUP, CRD_VERSION, RESOURCE_PLURAL,
        endpoint_name, namespace="default",
    )
    k8s.create_custom_resource(ref, resource_data)
    cr = k8s.wait_resource_consumed_by_controller(ref)

    assert cr is not None
    assert k8s.get_resource_exists(ref)

    # S3 target endpoints reach active status synchronously — wait for sync.
    assert k8s.wait_on_condition(
        ref, "ACK.ResourceSynced", "True",
        wait_periods=MAX_WAIT_FOR_SYNCED_MINUTES * 4, period_length=15,
    )

    yield ref, cr, endpoint_name



# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

@service_marker
class TestEndpoint:

    def test_crud(self, endpoint):
        """Verifies the full Create → Read → Update → Delete lifecycle.

        Checks:
        1.  After creation the K8s CR has ``ACK.ResourceSynced=True`` and the
            DMS API reports the endpoint as ``active``.
        2.  The AWS API matches the spec fields: identifier, endpoint type,
            engine name, and initial bucket folder. The ARN is written into
            the CR status by the controller.
        3.  The ACK system tags are present in the AWS API after creation.
        4.  Tags can be added (``environment=dev``), updated
            (``environment=prod``), and deleted; the AWS API reflects each
            change after re-sync.
        5.  ``s3Settings.bucketFolder`` can be updated; the AWS API reflects
            the new value after re-sync.
        """
        ref, cr, endpoint_name = endpoint

        # ---- Verify create / read ------------------------------------------
        condition.assert_synced(ref)

        latest = aws_api.get(endpoint_name)
        assert latest is not None
        assert latest['EndpointIdentifier'] == endpoint_name
        assert latest['EndpointType'] == 'TARGET'
        assert latest['EngineName'] == 's3'
        assert latest['Status'] == 'active'
        assert latest.get('S3Settings', {}).get('BucketFolder') == INITIAL_BUCKET_FOLDER

        # ARN is written into the CR status by the controller.
        cr = k8s.get_resource(ref)
        assert cr is not None
        endpoint_arn = k8s.get_resource_arn(cr)
        assert endpoint_arn is not None

        # ---- Verify initial tags -------------------------------------------
        latest_tags = aws_api.get_tags(endpoint_arn)
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
        latest_tags = aws_api.get_tags(endpoint_arn)
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
        latest_tags = aws_api.get_tags(endpoint_arn)
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
        latest_tags = aws_api.get_tags(endpoint_arn)
        assert latest_tags is not None
        tags.assert_ack_system_tags(latest_tags)
        tags.assert_equal_without_ack_tags(expect_tags, latest_tags)

        # ---- Update: s3Settings.bucketFolder --------------------------------
        k8s.patch_custom_resource(
            ref,
            {"spec": {"s3Settings": {"bucketFolder": UPDATED_BUCKET_FOLDER}}},
        )
        time.sleep(MODIFY_WAIT_AFTER_SECONDS)

        assert k8s.wait_on_condition(
            ref, "ACK.ResourceSynced", "True",
            wait_periods=MAX_WAIT_FOR_SYNCED_MINUTES * 4, period_length=15,
        )

        latest = aws_api.get(endpoint_name)
        assert latest is not None
        assert latest.get('S3Settings', {}).get('BucketFolder') == UPDATED_BUCKET_FOLDER
