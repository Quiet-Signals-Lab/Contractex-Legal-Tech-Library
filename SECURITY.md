# Security policy

## Reporting a vulnerability

Email **hello@quietsignalslab.com** with "Contractex security" in the subject
line.  Please do not open a public issue.

Include the Contractex version, a minimal reproduction using synthetic text,
and what an attacker or a mistake could achieve.  Reports are acknowledged by
email.  Contractex is maintained by one person, so there is no guaranteed
response time.  Fixes are released as soon as they are ready and credited in
the changelog unless you ask otherwise.

## In scope

- Any way for the text of a document to reach a model against its
  `PrivacyProfile`: a `secret` document reaching any provider, a `restricted`
  document reaching a provider other than `LocalProvider`, or unredacted
  `confidential` text.
- Personal data in a format the regex fallback claims to handle surviving
  redaction.
- Weaknesses in `HASH` or `ENCRYPT` redaction, or in how redaction maps are
  handled.
- Vulnerabilities in Contractex's own code or its packaging.

## Out of scope

- Limitations already documented on the
  [Limitations](https://quietsignalslab.com/contractex/docs/limitations/) page,
  such as names not being detected without Presidio.
- Vulnerabilities in model providers' services, or in dependencies, unless
  Contractex uses them unsafely.

## Supported versions

Only the latest release on PyPI receives fixes.
