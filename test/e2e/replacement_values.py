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
"""Stores the values used by each of the integration tests for replacing the
Database Migration Service-specific test variables.
"""
from acktest.aws import identity
from e2e.bootstrap_resources import get_bootstrap_resources

BOOTSTRAP_RESOURCES = get_bootstrap_resources()

REPLACEMENT_VALUES = {
    # S3 bucket and IAM role used by Endpoint (S3 target) tests.
    "S3_BUCKET_NAME": BOOTSTRAP_RESOURCES.TestBucket.name,
    # The test bucket is bootstrapped in the current AWS account.
    "S3_BUCKET_OWNER": identity.get_account_id(),
    "DMS_S3_ROLE_ARN": BOOTSTRAP_RESOURCES.TestEndpointRole.arn,
}
