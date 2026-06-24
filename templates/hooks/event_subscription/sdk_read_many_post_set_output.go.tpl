
// sdk_read_many_post_set_output hook
//
// The API does not return the ARN so we build it ourselves.
if ko.Status.ACKResourceMetadata == nil {
    ko.Status.ACKResourceMetadata = &ackv1alpha1.ResourceMetadata{}
}
if ko.Status.ACKResourceMetadata.ARN == nil {
    arn := ackv1alpha1.AWSResourceName(fmt.Sprintf(
        "arn:%s:dms:%s:%s:es:%s",
        rm.awsPartition,
        rm.awsRegion,
        rm.awsAccountID,
        *ko.Spec.Name,
    ))
    ko.Status.ACKResourceMetadata.ARN = &arn
}

// sdk_read_many_post_set_output hook
//
// Retrieves the latest tags.
if ko.ObjectMeta.GetDeletionTimestamp() == nil {
    if ko.Status.ACKResourceMetadata != nil && ko.Status.ACKResourceMetadata.ARN != nil {
        resourceARN := (*string)(ko.Status.ACKResourceMetadata.ARN)
        tags, err := rm.getTags(ctx, *resourceARN)
        if err != nil {
            return nil, err
        }
        ko.Spec.Tags = tags
    }
}
