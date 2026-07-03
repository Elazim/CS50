from app.ai.pii import detect_pii


def test_detects_insurance_identifiers():
    text = (
        "Contact rita.moreno@example.com or 555-201-8890 about POL-4482911 "
        "and CLM-2201435. SSN on file: 123-45-6789. DOB: 04/12/1988."
    )
    types = {s.type for s in detect_pii(text)}
    assert types == {"email", "phone", "policy_number", "claim_number", "ssn", "dob"}


def test_previews_are_masked():
    spans = detect_pii("email me at someone@example.com")
    assert all("@" not in s.preview[1:] for s in spans)
    assert all("*" in s.preview for s in spans)


def test_clean_text_yields_nothing():
    assert detect_pii("The supervisor reviews the assignment queue each morning.") == []
