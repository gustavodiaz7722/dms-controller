# Copyright Amazon.com Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"). You may
# not use this file except in compliance with the License. A copy of the
# License is located at
#
#	 http://aws.amazon.com/apache2.0/
#
# or in the "license" file accompanying this file. This file is distributed
# on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either
# express or implied. See the License for the specific language governing
# permissions and limitations under the License.

"""Utilities for working with DMS replication subnet resources"""

import datetime
import time

import boto3
import pytest

DEFAULT_WAIT_UNTIL_DELETED_TIMEOUT_SECONDS = 60 * 10
DEFAULT_WAIT_UNTIL_DELETED_INTERVAL_SECONDS = 15


def wait_until_deleted(
    subnet_group_id: str,
    timeout_seconds: int = DEFAULT_WAIT_UNTIL_DELETED_TIMEOUT_SECONDS,
    interval_seconds: int = DEFAULT_WAIT_UNTIL_DELETED_INTERVAL_SECONDS,
) -> None:
    """Waits until a DMS ReplicationSubnetGroup is no longer returned by the API.

    Raises:
        pytest.fail upon timeout.
    """
    now = datetime.datetime.now()
    timeout = now + datetime.timedelta(seconds=timeout_seconds)

    while True:
        if datetime.datetime.now() >= timeout:
            pytest.fail(
                "Timed out waiting for ReplicationSubnetGroup to be "
                "deleted in DMS API"
            )

        latest = get(subnet_group_id)
        if latest is None:
            break

        time.sleep(interval_seconds)


def get(subnet_group_id):
    """Returns a dict containing the DMS replication_subnet_group record from the DMS API.

    If no such DMS replication_subnet_group exists, returns None.
    """
    c = boto3.client('dms')
    try:
        resp = c.describe_replication_subnet_groups(
            Filters=[
                {
                    'Name': 'replication-subnet-group-id',
                    'Values': [
                        subnet_group_id,
                    ]
                },
            ],
        )
        assert len(resp['ReplicationSubnetGroups']) == 1
        return resp['ReplicationSubnetGroups'][0]
    except c.exceptions.ResourceNotFoundFault:
        return None


def get_tags(subnet_group_arn):
    """Returns a dict containing the DMS replication subnet group's tag records from the DMS
    API.

    If no such DMS replication subnet group exists, returns None.
    """
    c = boto3.client('dms')
    try:
        resp = c.list_tags_for_resource(
            ResourceArn=subnet_group_arn,
        )
        return resp['TagList']
    except c.exceptions.ResourceNotFoundFault:
        return None
