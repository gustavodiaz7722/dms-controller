
// sdk_delete_pre_build_request hook
//
// Do not attempt to delete the endpoint if it is already in the
// process of being deleted.
if r.ko.Status.EndpointStatus != nil && *r.ko.Status.EndpointStatus == endpointStatusDeleting {
    return r, ackrequeue.NeededAfter(
        errors.New(fmt.Sprintf("Endpoint is in %v state", *r.ko.Status.EndpointStatus)),
        10*time.Second)
}
