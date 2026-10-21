# Reference data

All code lists used by the agents live here as JSON so business users can
update them without code changes. **Several of these are illustrative
placeholders copied from the mockup** and must be replaced with licensed /
authoritative data before production:

| File | Used by | Production source |
|---|---|---|
| `cob_codes.json` | COB normalisation, validation | Your Lloyd's class-of-business / risk code list |
| `tmc_codes.json` | TMC enrichment | Mockup codes (TMC-110 …) are invented. Replace with Lloyd's risk codes / your internal taxonomy |
| `currencies.json` | Currency validation | ISO 4217 |
| `fx_rates.json` | FX normalisation | Lloyd's / Bank of England / ECB rates, ideally by rate date |
| `countries.json` | Country normalisation | ISO 3166-1 alpha-2 |
| `broker_aliases.json` | Broker normalisation | Your broker master data |
| `claim_status.json` | Claim status taxonomy | LCRS status list |
| `cresta_zones_sample.json` | CRESTA assignment | Licensed CRESTA zone data (cresta.org) + a geocoder |
