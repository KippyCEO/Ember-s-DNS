# Ember's DNS

Curated, categorized DNS blocklists from Ember's DNS (Avery and Ember's Technologies). Block ads, trackers, malware, phishing, scams, and more on Pi-hole, AdGuard Home, and other DNS filters.

## How to use

1. Pick the categories you want from the list table below.
2. Add each URL as a blocklist/adlist in your DNS filter:
   - **Pi-hole:** Group Management → Adlists → paste the URL → Add → run `pihole -g` (Update Gravity).
   - **AdGuard Home:** Filters → DNS blocklists → Add blocklist → Add a custom list → paste the URL.
   - **Other tools:** Any resolver that accepts hosts-format blocklists by URL will work.
3. Start with **Ad networks**, **Analytics & Telemetry**, and **Malware** for solid everyday protection. Add the rest to taste.

> Heads up: some categories (Gambling, Drugs, Piracy, Torrent, Redirect) can break sites you actually use. Enable them deliberately and keep an allowlist handy.

## Ready-to-use lists (rebuilt daily)

Ember's DNS downloads our source lists once a day, strips comments, normalizes the format to plain domains, removes duplicates, and publishes the result here. Subscribe to any of these:

<!-- BUILT-LISTS:START -->
| Category | Domains | Subscribe URL |
|---|---|---|
| Ad networks & services | 268,178 | `https://raw.githubusercontent.com/KippyCEO/Ember-s-DNS/main/lists/ad-networks-services.txt` |
| Analytics & Telemetry | 8,926 | `https://raw.githubusercontent.com/KippyCEO/Ember-s-DNS/main/lists/analytics-telemetry.txt` |
| Malware, Phishing, Scams | 1,581,012 | `https://raw.githubusercontent.com/KippyCEO/Ember-s-DNS/main/lists/malware-phishing-scams.txt` |
| PUP | 55,168 | `https://raw.githubusercontent.com/KippyCEO/Ember-s-DNS/main/lists/pup.txt` |
| Piracy | 2,154 | `https://raw.githubusercontent.com/KippyCEO/Ember-s-DNS/main/lists/piracy.txt` |
| Ransomware | 1,904 | `https://raw.githubusercontent.com/KippyCEO/Ember-s-DNS/main/lists/ransomware.txt` |
| Fraud | 285,200 | `https://raw.githubusercontent.com/KippyCEO/Ember-s-DNS/main/lists/fraud.txt` |
| Drugs | 26,029 | `https://raw.githubusercontent.com/KippyCEO/Ember-s-DNS/main/lists/drugs.txt` |
| Ads | 235,901 | `https://raw.githubusercontent.com/KippyCEO/Ember-s-DNS/main/lists/ads.txt` |
| Abuse | 435,119 | `https://raw.githubusercontent.com/KippyCEO/Ember-s-DNS/main/lists/abuse.txt` |
| Redirect | 108,685 | `https://raw.githubusercontent.com/KippyCEO/Ember-s-DNS/main/lists/redirect.txt` |
| Scam | 8,527 | `https://raw.githubusercontent.com/KippyCEO/Ember-s-DNS/main/lists/scam.txt` |
| Torrent | 2,620 | `https://raw.githubusercontent.com/KippyCEO/Ember-s-DNS/main/lists/torrent.txt` |
| Tracking | 143,876 | `https://raw.githubusercontent.com/KippyCEO/Ember-s-DNS/main/lists/tracking.txt` |
| Gambling | 342,623 | `https://raw.githubusercontent.com/KippyCEO/Ember-s-DNS/main/lists/gambling.txt` |
<!-- BUILT-LISTS:END -->

Each file is a plain list of domains (one per line), which works in Pi-hole, AdGuard Home, and most other DNS filters. `stats.json` has the latest counts.

## The updater

[`updater/`](updater) contains the small Python app (with a GUI) that does the daily build and push. See [`updater/README.md`](updater/README.md).

## Sources

View our sources here: [Ember's DNS source list](https://workdrive.zohopublic.com/sheet/open/65qe26d5d1b446f784448ac45022cbad0ddfc)

Third-party license notices are in [NOTICE.md](NOTICE.md).

## Contributing

Found a dead link, a false positive, or a great list we should add? Open an issue or pull request. Please include the list's license so we can keep everything properly attributed.

## License

The contents of this repository (README, metadata, and scripts) are released under the [MIT License](LICENSE). Linked blocklists remain under their own licenses, listed above.

---

Made with ❤️ by Avery and Ember's Technologies.
