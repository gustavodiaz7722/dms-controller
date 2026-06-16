
// sdk_read_many_post_set_output hook
//
// Retrieves the latest tags.
if ko.Status.ACKResourceMetadata != nil && ko.Status.ACKResourceMetadata.ARN != nil && ko.ObjectMeta.GetDeletionTimestamp() == nil {
    resourceARN := (*string)(ko.Status.ACKResourceMetadata.ARN)
    tags, err := rm.getTags(ctx, *resourceARN)
    if err != nil {
        return nil, err
    }
    ko.Spec.Tags = tags
}

// sdk_read_many_post_set_output hook
//
// Ensure EndpointType is assigned in lower-case. DMS Endpoint API has a
// case-mismatch between input and output EndpointType. All *Endpoint APIs
// return EndpointType in upper-case while CreateEndpoint and ModifyEndpoint
// expect its input in lower-case.
if ko.Spec.EndpointType != nil {
    lowerEndpointType := strings.ToLower(*ko.Spec.EndpointType)
    ko.Spec.EndpointType = aws.String(lowerEndpointType)
}
