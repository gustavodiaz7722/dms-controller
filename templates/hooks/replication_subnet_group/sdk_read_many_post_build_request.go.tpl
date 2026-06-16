
// sdk_read_many_post_build_request hook
//
// DescribeReplicationSubnetGroups does not provide any identifier input fields,
// so we need to build a filter on our own.
input.Filters = []svcsdktypes.Filter{
    {
        Name: aws.String("replication-subnet-group-id"),
        Values: []string{aws.ToString(r.ko.Spec.Name)},
    },
}
