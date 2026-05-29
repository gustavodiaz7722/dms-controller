
// sdk_create_post_build_request hook
//
// Setting CertificateWallet from custom field
if desired.ko.Spec.CertificateWallet != nil {
    tmpSecret, err := rm.rr.SecretValueFromReference(ctx, desired.ko.Spec.CertificateWallet)
    if err != nil {
        return nil, ackrequeue.Needed(err)
    }
    if tmpSecret != "" {
        input.CertificateWallet = []byte(tmpSecret)
    }
}
