
// sdk_delete_post_request hook
//
// Wait for the event subscription to be deleted before
// setResourceUnmanaged.
if err != nil {
    return nil, err
}
r.ko.Status.SubscriptionStatus = aws.String(eventSubscriptionStatusDeleting)
return r, ackrequeue.NeededAfter(
    errors.New(fmt.Sprintf("EventSubscription is in %v state", *r.ko.Status.SubscriptionStatus)),
    10*time.Second)
