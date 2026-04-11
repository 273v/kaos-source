# Forensic/eDiscovery Test Fixtures

Real-world email and forensic test data from public sources.  All files
are from publicly available corpora with permissive licensing.

## Enron Email Corpus (5 files)

Source: CALO/CMU Enron Email Dataset
https://www.cs.cmu.edu/~enron/

These are real messages from Enron custodian Brad McKay (`mckay-b`),
part of the FERC public record released during the Enron investigation.
Extracted from `enron_mail_20150507.tar.gz`.

All files retain the forensic metadata added by the Enron processing
pipeline:
- `X-Origin` — custodian identifier (e.g., `McKay-B`)
- `X-Folder` — original Notes folder path (e.g., `\Bradley_McKay_Dec2000\Notes Folders\Notes inbox`)
- `X-FileName` — original NSF filename (e.g., `bmckay.nsf`)
- `X-From` / `X-To` / `X-cc` — display names separated from envelope addresses

| File | Size | Type | Why it's useful |
|------|------|------|-----------------|
| `enron_legal_dept.eml` | 1.4KB | Corp announcement | Wholesale Services Legal Department reorganization — real legal/compliance content |
| `enron_inbound_offers.eml` | 913B | Internal business | Short inbound from james.barker@enron.com |
| `enron_forward_external.eml` | 2.2KB | Forwarded external | Personal email forwarded to Enron account (eDiscovery: personal use of company email) |
| `enron_mckay_reply.eml` | 718B | Outbound reply | Brad McKay's sent reply — tests custodian identification |
| `enron_mckay_fishing.eml` | 576B | Personal reply | Personal content on company email |

**License**: FERC public record (released during the Enron investigation).
Free for research use.

## GOVCERT-LU eml_parser samples (4 files)

Source: https://github.com/GOVCERT-LU/eml_parser/tree/master/samples
License: BSD 2-Clause

Curated edge cases for testing EML parsing.

| File | Size | Purpose |
|------|------|---------|
| `govcert_sample.eml` | 399B | Minimal valid RFC 5322 message |
| `govcert_sample_attachments.eml` | 15KB | Multiple attachments |
| `govcert_sample_mime_attachment_html.eml` | 2.2KB | HTML body + attachment |
| `govcert_sample_mime_inline_html.eml` | 2.1KB | Inline HTML (no attachment) |

## SpamScope mail-parser samples (4 files)

Source: https://github.com/SpamScope/mail-parser/tree/develop/tests/mails
License: Apache 2.0

Real-world spam/phishing samples with full header sets — useful for
testing forensic header analysis (Received chains, Return-Path, etc.).

| File | Size | Content |
|------|------|---------|
| `spamscope_mail_test_12.eml` | 795B | Short with Return-Path, simple body |
| `spamscope_mail_test_14.eml` | 802B | Basic test message |
| `spamscope_mail_test_17.eml` | 5.7KB | Full Received chain, multi-hop routing |
| `spamscope_mail_malformed_2.eml` | 2.2KB | Malformed headers (regression case) |

## Apache Software Foundation mailing list (1 MBOX)

Source: https://lists.apache.org/api/mbox.lua?list=dev&domain=forrest.apache.org&d=2012-12
License: Public record (ASF mailing list archives are public)

Real open-source project development mailing list in MBOX format.

| File | Size | Content |
|------|------|---------|
| `apache_forrest_dev_2012_12.mbox` | 23KB | 5 messages from Apache Forrest dev list, December 2012 — includes JIRA notifications, release discussions, and CI failure reports. Real threading via In-Reply-To. |
