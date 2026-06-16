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

"""Utilities for working with DMS Endpoint resources."""

import datetime
import time
import typing

import boto3
import pytest

DEFAULT_WAIT_UNTIL_TIMEOUT_SECONDS = 60 * 10
DEFAULT_WAIT_UNTIL_INTERVAL_SECONDS = 10
DEFAULT_WAIT_UNTIL_DELETED_TIMEOUT_SECONDS = 60 * 10
DEFAULT_WAIT_UNTIL_DELETED_INTERVAL_SECONDS = 10

EndpointMatchFunc = typing.Callable[[dict | None], bool]


class StatusMatcher:
    """Callable that returns True when an Endpoint matches a given status."""

    def __init__(self, status: str):
        self.match_on = status

    def __call__(self, record: dict | None) -> bool:
        return (
            record is not None
            and 'Status' in record
            and record['Status'] == self.match_on
        )


def status_matches(status: str) -> EndpointMatchFunc:
    """Returns a match function that checks for the given status string."""
    return StatusMatcher(status)


def wait_until(
    endpoint_name: str,
    match_fn: EndpointMatchFunc,
    timeout_seconds: int = DEFAULT_WAIT_UNTIL_TIMEOUT_SECONDS,
    interval_seconds: int = DEFAULT_WAIT_UNTIL_INTERVAL_SECONDS,
) -> None:
    """Waits until a DMS Endpoint matches the supplied predicate.

    Raises:
        pytest.fail upon timeout.
    """
    now = datetime.datetime.now()
    timeout = now + datetime.timedelta(seconds=timeout_seconds)

    while not match_fn(get(endpoint_name)):
        if datetime.datetime.now() >= timeout:
            pytest.fail("Failed to match Endpoint before timeout")
        time.sleep(interval_seconds)


def wait_until_deleted(
    endpoint_name: str,
    timeout_seconds: int = DEFAULT_WAIT_UNTIL_DELETED_TIMEOUT_SECONDS,
    interval_seconds: int = DEFAULT_WAIT_UNTIL_DELETED_INTERVAL_SECONDS,
) -> None:
    """Waits until a DMS Endpoint is no longer returned by the API.

    Raises:
        pytest.fail upon timeout.
    """
    now = datetime.datetime.now()
    timeout = now + datetime.timedelta(seconds=timeout_seconds)

    while True:
        if datetime.datetime.now() >= timeout:
            pytest.fail(
                "Timed out waiting for Endpoint to be deleted in DMS API"
            )

        latest = get(endpoint_name)
        if latest is None:
            break

        time.sleep(interval_seconds)


def get(endpoint_name: str) -> dict | None:
    """Returns the DMS Endpoint record for the supplied endpoint identifier.

    The controller filters DescribeEndpoints by ``endpoint-id``, matching the
    hook in ``sdk_read_many_post_build_request.go.tpl``.

    Returns None when no matching endpoint exists.
    """
    c = boto3.client('dms')
    try:
        resp = c.describe_endpoints(
            Filters=[
                {
                    'Name': 'endpoint-id',
                    'Values': [endpoint_name],
                }
            ]
        )
        endpoints = resp.get('Endpoints', [])
        if not endpoints:
            return None
        assert len(endpoints) == 1
        return endpoints[0]
    except c.exceptions.ResourceNotFoundFault:
        return None


def get_tags(endpoint_arn: str) -> list | None:
    """Returns the tag list for a DMS Endpoint.

    Returns None when the endpoint does not exist.
    """
    c = boto3.client('dms')
    try:
        resp = c.list_tags_for_resource(ResourceArn=endpoint_arn)
        return resp['TagList']
    except c.exceptions.ResourceNotFoundFault:
        return None
