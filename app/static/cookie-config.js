document.addEventListener('DOMContentLoaded', function () {
    document.documentElement.classList.add('cc--darkmode');

    CookieConsent.run({
        guiOptions: {
            consentModal: {
                layout: "box",
                position: "bottom right",
                equalWeightButtons: true,
                flipButtons: false
            },
            preferencesModal: {
                layout: "box",
                position: "bottom right",
                equalWeightButtons: true,
                flipButtons: false
            }
        },
        categories: {
            necessary: {
                readOnly: true
            },
        },
        language: {
            default: "en",
            autoDetect: "browser",
            translations: {
                en: {
                    consentModal: {
                        title: "This site uses cookies",
                        description: "We use cookies to keep you signed in and remember your login preferences. These are required for the website to function.",
                        acceptAllBtn: "Got it",
                        acceptNecessaryBtn: "Reject all",
                        showPreferencesBtn: "More details",
                        footer: "<a href=/static/privacy_policy.html>Privacy Policy</a>\n<a href=/static/terms_and_conditions.html>Terms and conditions</a>"
                    },
                    preferencesModal: {
                        title: "Consent Preferences Center",
                        acceptAllBtn: "Accept all",
                        acceptNecessaryBtn: "Reject all",
                        savePreferencesBtn: "Save preferences",
                        closeIconLabel: "Close modal",
                        serviceCounterLabel: "Service|Services",
                        sections: [
                            {
                                title: "Essential Login Cookies <span class=\"pm__badge\">Always Enabled</span>",
                                description: `
                                    <strong>session</strong> - Your login session, application would not function without this<br>
                                    <strong>remember_token</strong> - "Remember me" functionality, allows you to stay logged in for a longer period of time<br>
                                    <strong>cc_cookie</strong> - Cookie Consent cookie, used to store your cookie consent preferences
                                `,
                                linkedCategory: "necessary"
                            }
                        ]
                    }
                }
            }
        }
    });
});