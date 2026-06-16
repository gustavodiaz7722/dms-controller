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

"""Integration tests for the DMS API ReplicationSubnetGroup resource.

Test scenarios
--------------
* test_crud
    Create a ReplicationSubnetGroup, verify it appears in the DMS API with the
    expected description. Wait for it to become synced, verify the K8s CR
    status and the AWS API, verify the initial tags, add/update/delete tags
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
from e2e.replacement_values import REPLACEMENT_VALUES
from e2e import replication_subnet_group as aws_api

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RESOURCE_PLURAL = 'replicationsubnetgroups'

# DMS ReplicationSubnetGroups are created synchronously — wait for sync.
MAX_WAIT_FOR_SYNCED_MINUTES = 5

# Pause between patching and re-checking so the controller can reconcile.
MODIFY_WAIT_AFTER_SECONDS = 10

SUBNET_GROUP_DESC = "my-replication-subnet-group description"

@pytest.fixture
def subnet_group(request):
    """Creates a ReplicationSubnetGroup K8s CR and tears it down afterward.

    The subnet group is created from the ``replication_subnet_group`` resource
    template using randomly-suffixed names to avoid collisions across parallel
    test runs.

    Yields:
        tuple: (ref, cr, subnet_group_name), where *ref* is the
        ``CustomResourceReference``, *cr* is the initial CR dict returned by
        the controller, and *subnet_group_name* is the identifier used for both
        the K8s object name and the DMS resource name.
    """
    ref = None
    subnet_group_name = None

    def _cleanup():
        """Deletes any resources created by this fixture.

        Registered as a finalizer so it runs even if fixture setup fails after
        creating the Kubernetes ReplicationSubnetGroup resource.
        """
        if ref is not None:
            try:
                if k8s.get_resource_exists(ref):
                    _, deleted = k8s.delete_custom_resource(ref, 3, 10)
                    assert deleted
            except Exception as e:
                logging.warning(f"failed to delete subnet group CR: {e}")

        if subnet_group_name is not None:
            try:
                aws_api.wait_until_deleted(subnet_group_name)
            except Exception as e:
                logging.warning(f"failed waiting for subnet group deletion: {e}")

    request.addfinalizer(_cleanup)

    subnet_group_name = random_suffix_name("my-replication-subnet-group", 33)

    replacements = REPLACEMENT_VALUES.copy()
    replacements["REPLICATION_SUBNET_GROUP_NAME"] = subnet_group_name
    replacements["REPLICATION_SUBNET_GROUP_DESC"] = SUBNET_GROUP_DESC

    resource_data = load_dms_resource(
        "replication_subnet_group",
        additional_replacements=replacements,
    )
    logging.debug(resource_data)

    ref = k8s.CustomResourceReference(
        CRD_GROUP, CRD_VERSION, RESOURCE_PLURAL,
        subnet_group_name, namespace="default",
    )
    k8s.create_custom_resource(ref, resource_data)
    cr = k8s.wait_resource_consumed_by_controller(ref)

    assert cr is not None
    assert k8s.get_resource_exists(ref)

    # ReplicationSubnetGroups are created synchronously in DMS — wait for sync.
    assert k8s.wait_on_condition(
        ref, "ACK.ResourceSynced", "True",
        wait_periods=MAX_WAIT_FOR_SYNCED_MINUTES * 4, period_length=15,
    )

    yield ref, cr, subnet_group_name



# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

@service_marker
class TestReplicationSubnetGroup:
    def test_crud(self, subnet_group):
        """Verifies the full Create → Read → Update → Delete lifecycle.

        Checks:
        1.  The subnet group is immediately visible in the DMS API after the
            K8s CR is consumed by the controller.
        2.  The ``ReplicationSubnetGroupDescription`` field matches the value
            set in the CR spec.
        3.  The initial ACK system tags are present on the resource.
        4.  Tags can be added as ``environment=dev`` via a CR patch.
        5.  Tags can be updated to ``environment=prod`` via a CR patch.
        6.  Tags can be deleted by patching ``tags`` to ``None``.
        """
        ref, cr, subnet_group_name = subnet_group

        # ---- Verify create / read ------------------------------------------
        condition.assert_synced(ref)

        latest = aws_api.get(subnet_group_name)
        assert latest is not None
        assert latest['ReplicationSubnetGroupDescription'] == SUBNET_GROUP_DESC

        # ARN is written into the CR status by the controller.
        cr = k8s.get_resource(ref)
        assert cr is not None
        subnet_group_arn = k8s.get_resource_arn(cr)
        assert subnet_group_arn is not None

        # ---- Verify initial tags -------------------------------------------
        latest_tags = aws_api.get_tags(subnet_group_arn)
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
        latest_tags = aws_api.get_tags(subnet_group_arn)
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
        latest_tags = aws_api.get_tags(subnet_group_arn)
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
        latest_tags = aws_api.get_tags(subnet_group_arn)
        assert latest_tags is not None
        tags.assert_ack_system_tags(latest_tags)
        tags.assert_equal_without_ack_tags(expect_tags, latest_tags)
