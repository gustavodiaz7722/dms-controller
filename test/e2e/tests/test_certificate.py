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

"""Integration tests for the DMS API Certificate resource.

Test scenarios
--------------
* test_crud
    Create a Certificate from a PEM certificate stored in a Kubernetes Secret.
    Wait for it to become synced, verify the K8s CR status and the AWS API,
    verify the initial tags, add/update/delete tags and let the fixture handle
    deletion.
"""

import datetime
import logging
import time

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from acktest import tags
from acktest.k8s import condition
from acktest.k8s import resource as k8s
from acktest.resources import random_suffix_name
from e2e import service_marker, CRD_GROUP, CRD_VERSION, load_dms_resource
from e2e import certificate as aws_api

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RESOURCE_PLURAL = "certificates"

# DMS certificates are created synchronously — wait for sync.
MAX_WAIT_FOR_SYNCED_MINUTES = 5

# Pause between patching and re-checking so the controller can reconcile.
MODIFY_WAIT_AFTER_SECONDS = 10

SECRET_KEY = "certificate.pem"


def _generate_self_signed_cert_pem() -> str:
    """Generates a minimal self-signed RSA certificate and returns it as a
    PEM-encoded string, for use as a test fixture."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "test-cert"),
    ])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=3650))
        .sign(key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def certificate(request):
    """Creates a Certificate CR with a test PEM certificate stored in a
    Kubernetes Secret and tears it down after the test.

    Yields:
        tuple: (ref, cr, certificate_name)
    """
    ref = None
    certificate_name = None
    secret_name = None

    def _cleanup():
        """Deletes any resources created by this fixture.

        Registered as a finalizer so it runs even if fixture setup fails after
        creating the Kubernetes Secret and/or Certificate resource.
        """
        if ref is not None:
            try:
                if k8s.get_resource_exists(ref):
                    _, deleted = k8s.delete_custom_resource(ref, 3, 10)
                    assert deleted
            except Exception as e:
                logging.warning(f"failed to delete certificate CR: {e}")

        if certificate_name is not None:
            try:
                aws_api.wait_until_deleted(certificate_name)
            except Exception as e:
                logging.warning(f"failed waiting for certificate deletion: {e}")

        if secret_name is not None:
            try:
                k8s.delete_secret("default", secret_name)
            except Exception as e:
                logging.warning(f"failed to delete certificate secret: {e}")

    request.addfinalizer(_cleanup)

    certificate_name = random_suffix_name("my-dms-certificate", 24)
    secret_name = random_suffix_name("dms-cert-secret", 21)

    # Create the Kubernetes Secret containing a freshly generated certificate PEM
    k8s.create_opaque_secret("default", secret_name, SECRET_KEY, _generate_self_signed_cert_pem())

    replacements = {
        "CERTIFICATE_NAME": certificate_name,
        "CERTIFICATE_SECRET_NAME": secret_name,
        "CERTIFICATE_SECRET_KEY": SECRET_KEY,
    }

    resource_data = load_dms_resource(
        "certificate",
        additional_replacements=replacements,
    )
    logging.debug(resource_data)

    ref = k8s.CustomResourceReference(
        CRD_GROUP, CRD_VERSION, RESOURCE_PLURAL,
        certificate_name, namespace="default",
    )
    k8s.create_custom_resource(ref, resource_data)
    cr = k8s.wait_resource_consumed_by_controller(ref)

    assert cr is not None
    assert k8s.get_resource_exists(ref)

    # Certificates are created synchronously in DMS — wait for sync.
    assert k8s.wait_on_condition(
        ref, "ACK.ResourceSynced", "True",
        wait_periods=MAX_WAIT_FOR_SYNCED_MINUTES * 4, period_length=15,
    )

    yield ref, cr, certificate_name



# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

@service_marker
class TestCertificate:

    def test_crud(self, certificate):
        """Verifies the full Create → Read → Update → Delete lifecycle.

        Checks:
        1.  After creation the K8s CR has ``ACK.ResourceSynced=True`` and the
            DMS API reports the certificate as existing.
        2.  The AWS API matches the spec fields: identifier.
        3.  The initial ACK system tags are present in the AWS API.
        4.  Tags can be added (``environment=dev``); the AWS API reflects the
            new value.
        5.  Tags can be updated from ``environment=dev`` to
            ``environment=prod``; the AWS API reflects the new value.
        6.  Tags can be deleted by patching ``tags`` to ``None``; the AWS API
            reflects only system tags with no user-defined tags remaining.
        """
        ref, cr, certificate_name = certificate

        # ---- Verify create / read ------------------------------------------
        condition.assert_synced(ref)

        latest = aws_api.get(certificate_name)
        assert latest is not None
        assert latest['CertificateIdentifier'] == certificate_name

        # ARN is written into the CR status by the controller.
        cr = k8s.get_resource(ref)
        assert cr is not None
        certificate_arn = k8s.get_resource_arn(cr)
        assert certificate_arn is not None

        # ---- Verify initial tags -------------------------------------------
        latest_tags = aws_api.get_tags(certificate_arn)
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
        latest_tags = aws_api.get_tags(certificate_arn)
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
        latest_tags = aws_api.get_tags(certificate_arn)
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
        latest_tags = aws_api.get_tags(certificate_arn)
        assert latest_tags is not None
        tags.assert_ack_system_tags(latest_tags)
        tags.assert_equal_without_ack_tags(expect_tags, latest_tags)
