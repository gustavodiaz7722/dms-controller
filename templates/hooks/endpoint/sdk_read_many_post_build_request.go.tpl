
// sdk_read_many_post_build_request hook
//
// DescribeEndpoints does not provide any identifier input fields,
// so we need to build a filter on our own.
input.Filters = []svcsdktypes.Filter{
    {
        Name: aws.String("endpoint-id"),
        Values: []string{aws.ToString(r.ko.Spec.Name)},
    },
}
