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
"""Bootstraps the resources required to run the Database Migration Service integration tests.
"""

import json
import logging

from acktest.bootstrapping import Resources, BootstrapFailureException
from acktest.bootstrapping.iam import Role, UserPolicies
from acktest.bootstrapping.s3 import Bucket
from acktest.bootstrapping.vpc import VPC

from e2e import bootstrap_directory
from e2e.bootstrap_resources import BootstrapResources

def service_bootstrap() -> Resources:
    logging.getLogger().setLevel(logging.INFO)

    # S3 bucket for DMS S3 endpoint and replication task tests.
    # Bucket.__post_init__() computes the random name before bootstrap() runs,
    # so we can reference bucket.name when building the IAM policy below.
    test_bucket = Bucket(name_prefix="ack-test-dms-bucket")

    s3_access_policy = json.dumps({
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "s3:ListBucket",
                    "s3:GetBucketLocation",
                    "s3:GetBucketAcl",
                ],
                "Resource": f"arn:aws:s3:::{test_bucket.name}",
            },
            {
                "Effect": "Allow",
                "Action": [
                    "s3:GetObject",
                    "s3:PutObject",
                    "s3:DeleteObject",
                    "s3:AbortMultipartUpload",
                    "s3:PutObjectTagging",
                ],
                "Resource": f"arn:aws:s3:::{test_bucket.name}/*",
            },
        ],
    })

    # UserPolicies is a Bootstrappable subresource; it will be bootstrapped
    # automatically when test_endpoint_role.bootstrap() is called.
    s3_policies = UserPolicies(
        name_prefix="ack-test-dms-s3-policy",
        policy_documents=[s3_access_policy],
    )

    test_endpoint_role = Role(
        name_prefix="ack-test-dms-s3-role",
        principal_service="dms.amazonaws.com",
        user_policies=s3_policies,
    )

    resources = BootstrapResources(
        TestBucket=test_bucket,
        TestEndpointRole=test_endpoint_role,
        TestVPC=VPC(name_prefix="ack-test-vpc", num_public_subnet=2, num_private_subnet=2),
    )

    try:
        resources.bootstrap()
    except BootstrapFailureException as ex:
        exit(254)

    return resources

if __name__ == "__main__":
    config = service_bootstrap()
    # Write config to current directory by default
    config.serialize(bootstrap_directory)
