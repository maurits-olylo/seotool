# Retentiebeleid

Versie: `2026-08-02-v1`

## Principes

- URL-identiteit, issues, taken, verificaties, comments, suppressions en auditgeschiedenis blijven
  bewaard zolang de klant bestaat.
- Retentie verwijdert alleen detail dat opnieuw kan ontstaan of waarvan voldoende historie blijft.
- Twee volledige jaarvergelijkingen moeten mogelijk blijven; dagelijkse integratiedata blijft
  daarom minimaal 1.098 dagen beschikbaar.
- Iedere automatische operatie is per website en datatype idempotent, begrensd en hervatbaar.
- Actieve crawls blokkeren retentie voor dezelfde website.
- Snapshots en wijzigingen worden wel geaudit, maar in deze beleidsversie niet automatisch
  verwijderd.

## Termijnen

| Data | Beleid |
|---|---|
| URL's en bronnen | Bewaren zolang de klant bestaat |
| Issues, occurrences, taken en verificaties | Permanent binnen de klantlevensduur |
| Activity- en taaklog | Permanent binnen de klantlevensduur |
| Elementlocaties | Actieve/laatste crawl, nieuwste URL-locatie en issues bewaren |
| Interne linkdetails | 180 dagen plus actieve, laatste volledige en bewijsdragende crawls |
| GSC pagina- en querydata | 1.098 dagen |
| GA4 pagina-, event- en pagina/eventdata | 1.098 dagen |
| Bing pagina- en querydata | 1.098 dagen |
| Crawlrunhistorie | Alleen audit; geen automatische verwijdering |
| URL-snapshots | Alleen audit; geen automatische verwijdering |
| Wijzigingen | Alleen audit; geen automatische verwijdering |
| Maandrapportages | Drie jaar volgens bestaande scheduler |

## Uitvoering

Een afgeronde volledige crawl maakt per automatisch datatype één `retention_operation`. De unieke
sleutel op crawlrun en datatype voorkomt duplicaten. Iedere operatie bewaart beleidsversie,
voorrapport, voortgang, aantal batches, verwijderde rijen, narapport, fouten en volgende poging.

De read-only audit toont per website leeftijdsbuckets, kandidaten en permanent beschermde
historie. Gebruik de audit vóór en na een productievenster. Een productiecleanup met werkelijk
oude rijen vereist een actuele geverifieerde back-up, een stagingproef en de veilige crawl-drain.

## Wijzigen van beleid

Pas termijnen alleen aan via een nieuwe beleidsversie, tests en documentatie. Verkort geen termijn
wanneer rapportage, jaarvergelijking, issuebewijs of verificatie daarvan afhankelijk is.
