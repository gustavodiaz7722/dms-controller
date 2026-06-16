
// sdk_update_pre_build_request hook
//
// Sync the latest tags.
if delta.DifferentAt("Spec.Tags") {
    if err = rm.syncTags(ctx, desired, latest); err != nil {
        return nil, err
    }
}
if !delta.DifferentExcept("Spec.Tags") {
    return desired, nil
}
