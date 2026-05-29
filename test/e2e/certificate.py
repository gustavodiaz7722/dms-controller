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

"""Utilities for working with DMS Certificate resources."""

import datetime
import time
import typing

import boto3
import pytest

DEFAULT_WAIT_UNTIL_TIMEOUT_SECONDS = 60 * 10
DEFAULT_WAIT_UNTIL_INTERVAL_SECONDS = 10
DEFAULT_WAIT_UNTIL_DELETED_TIMEOUT_SECONDS = 60 * 10
DEFAULT_WAIT_UNTIL_DELETED_INTERVAL_SECONDS = 10


def wait_until_deleted(
    certificate_id: str,
    timeout_seconds: int = DEFAULT_WAIT_UNTIL_DELETED_TIMEOUT_SECONDS,
    interval_seconds: int = DEFAULT_WAIT_UNTIL_DELETED_INTERVAL_SECONDS,
) -> None:
    """Waits until a DMS Certificate is no longer returned by the API.

    Raises:
        pytest.fail upon timeout.
    """
    now = datetime.datetime.now()
    timeout = now + datetime.timedelta(seconds=timeout_seconds)

    while True:
        if datetime.datetime.now() >= timeout:
            pytest.fail(
                "Timed out waiting for Certificate to be deleted in DMS API"
            )

        latest = get(certificate_id)
        if latest is None:
            break

        time.sleep(interval_seconds)


def get(certificate_id: str) -> dict | None:
    """Returns the DMS Certificate record for the supplied certificate identifier.

    The controller filters DescribeCertificates by ``certificate-arn``, matching the
    hook in ``sdk_read_many_post_build_request.go.tpl``.

    Returns None when no matching certificate exists.
    """
    c = boto3.client('dms')
    try:
        resp = c.describe_certificates(
            Filters=[
                {
                    'Name': 'certificate-id',
                    'Values': [certificate_id],
                }
            ]
        )
        certificates = resp.get('Certificates', [])
        if not certificates:
            return None
        assert len(certificates) == 1
        return certificates[0]
    except c.exceptions.ResourceNotFoundFault:
        return None


def get_tags(certificate_arn: str) -> list | None:
    """Returns the tag list for a DMS Certificate.

    Returns None when the certificate does not exist.
    """
    c = boto3.client('dms')
    try:
        resp = c.list_tags_for_resource(ResourceArn=certificate_arn)
        return resp['TagList']
    except c.exceptions.ResourceNotFoundFault:
        return None
