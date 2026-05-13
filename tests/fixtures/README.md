# kaos-source top-level test fixtures

Fixtures used directly by `kaos-source`'s unit, integration, and e2e
tests. Sub-corpora (forensic email, etc.) have their own per-directory
READMEs:

- `forensics/README.md` — 14 EML/MBOX files (Enron, GOVCERT-LU,
  SpamScope, Apache Forrest) used by `parsers/email/`.

This README covers files that live at the top level of `tests/fixtures/`.

## PACER docket snapshot (1 file)

Source: saved MHTML snapshot of CAND ECF docket report for case
**3:24-cv-08437-SI** (U.S. District Court, Northern District of
California, San Francisco — Judge Susan Illston). Captured via
Chromium "Save as MHTML" on 2025-07-11 from
`https://ecf.cand.uscourts.gov/cgi-bin/DktRpt.pl?611847327892323-L_1_0-1`.

PACER docket reports are records of the U.S. federal courts. The
document content itself is government work product — public-domain
under 17 USC §105. The PACER service charges a per-page access fee,
but the underlying federal record carries no copyright.

| File | Source URL | License | Retrieved | SHA-256 | Notes |
|---|---|---|---|---|---|
| `pacer_docket1.html` | `https://ecf.cand.uscourts.gov/cgi-bin/DktRpt.pl?611847327892323-L_1_0-1` | public-domain (17 USC §105) — federal court record | 2025-07-11 (snapshot); 2026-04-04 (committed) | `e4dd4cfa9c425d8f676f1182282b3c39f4c1f010a69356b1fde0763f7b12dc0b` | CAND case 3:24-cv-08437-SI before Judge Susan Illston. MHTML Blink snapshot (quoted-printable-encoded HTML). 99,830 bytes. Used by `tests/unit/test_pacer.py`, `tests/integration/test_battle.py`, and `tests/e2e_smoke.py`. |

**Provenance notes**
- The MHTML wrapper preserves the original
  `Snapshot-Content-Location` header pointing at the live ECF URL —
  treat that header as the canonical source pointer.
- No PII redaction was applied: PACER docket reports are the public
  record and parties are identified by name on every line of the
  docket itself. This is the same narrowly-justified exception that
  applies to the Enron FERC corpus in `forensics/`; it is not a
  pattern to extend to other corpora.
- No customer / client / privileged content. The case was selected
  for fixture use because it exercises the PACER docket parser's
  edge cases (multi-attachment entries, hyperlinked doc1 references),
  not because of any 273V engagement.
