
// sdk_read_many_post_set_output hook
//
// Retrieves the latest tags.
if ko.Status.ACKResourceMetadata != nil && ko.Status.ACKResourceMetadata.ARN != nil {
    resourceARN := (*string)(ko.Status.ACKResourceMetadata.ARN)
    tags, err := rm.getTags(ctx, *resourceARN)
    if err != nil {
        return nil, err
    }
    ko.Spec.Tags = tags
}
